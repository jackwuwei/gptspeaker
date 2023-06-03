#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Jack Wu. All rights reserved.
# Licensed under the BSD license. See LICENSE.md file in the project root for full license information.
"""
Smart Speaker using Azure Speech SDK and OpenAI ChatGPT API
"""
import os
import azure.cognitiveservices.speech as speechsdk
import openai
import asyncio
import json
from collections import namedtuple
import tiktoken

EOF = object()

# Load config.json
def load_config():
    try:
        with open('config.json') as f:
            config = json.load(f, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
            if not config.AzureCognitiveServices.Key or not config.AzureCognitiveServices.Region or not config.OpenAI.Key:
                raise ValueError("Missing required configuration.")
            return config
    except FileNotFoundError:
        print("Error: config file not found.")
    except Exception as e:
        print(f"Error loading config: {e}")

# If tokens greater than 4096, then remove history message
def truncate_conversation(conversation, max_tokens):
    total_tokens = 0
    truncated_conversation = []
    encoding = tiktoken.get_encoding("cl100k_base")

    for message in reversed(conversation):
        message_tokens = len(encoding.encode(message['content']))
        if total_tokens + message_tokens > max_tokens - 100: 
            print(f'Total tokens is limit {total_tokens + message_tokens}')
            break
        total_tokens += message_tokens
        truncated_conversation.append(message)

    conversation = list(reversed(truncated_conversation))

# Prompts OpenAI with a request and async send sentences to queue.
async def ask_openai_async(model, prompt, max_token, conversation, queue, ending):
    # Append user questions
    conversation.append({"role":"user","content":prompt}) 

    # Count token limit and remove early histroy conversation 
    truncate_conversation(conversation, max_token)
    print(conversation)
    
    # Save one sentence
    collected_messages = ""

    # Save whole GPT answer
    full_answer = ""

    # Ask OpenAI
    response = await openai.ChatCompletion.acreate(model=model, 
                                                   messages=conversation,
                                                   stream=True)
    
    # iterate through the stream of events
    async for chunk in response:
        chunk_message = chunk['choices'][0]['delta'].get('content', '').replace('\n', ' ').strip()  # extract the message
        if not chunk_message:
            continue

        collected_messages += chunk_message  # save the message
        if collected_messages.endswith(ending): # One sentence
            print(f"ChatGPT Message received: {collected_messages}")
            await queue.put(collected_messages)
            full_answer += collected_messages
            collected_messages = ""

    # Save history message for continuous conversations
    conversation.append({"role":"assistant","content":full_answer})

# async read message from queue and synthesized speech
async def text_to_speech_async(speech_synthesizer, queue):
    while True:
        text = await queue.get()
        if text is EOF:
            break

        # Azure text to speech output
        speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()

        # Check result
        if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("Speech synthesized to speaker for text [{}]".format(text))
        elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = speech_synthesis_result.cancellation_details
            print("Speech synthesis canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print("Error details: {}".format(cancellation_details.error_details))

# Detect keyword and wakeup
def detect_keyword(model, keyword):
    # Create a local keyword recognizer with the default microphone device for input.
    keyword_recognizer = speechsdk.KeywordRecognizer()

    done = False

    def recognized_cb(evt):
        # Only a keyword phrase is recognized. The result cannot be 'NoMatch'
        # and there is no timeout. The recognizer runs until a keyword phrase
        # is detected or recognition is canceled (by stop_recognition_async()
        # or due to the end of an input file or stream).
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedKeyword:
            print("RECOGNIZED KEYWORD: {}".format(result.text))
        nonlocal done
        done = True

    def canceled_cb(evt):
        result = evt.result
        if result.reason == speechsdk.ResultReason.Canceled:
            print('CANCELED: {}'.format(result.cancellation_details.reason))
        nonlocal done
        done = True

    # Connect callbacks to the events fired by the keyword recognizer.
    keyword_recognizer.recognized.connect(recognized_cb)
    keyword_recognizer.canceled.connect(canceled_cb)

    # Start keyword recognition.
    result_future = keyword_recognizer.recognize_once_async(model)
    print('Say something starting with "{}" followed by whatever you want...'.format(keyword))
    result = result_future.get()

    # Read result audio (incl. the keyword).
    return result.reason == speechsdk.ResultReason.RecognizedKeyword

# Continuously listens for speech input to recognize and send as text to Azure OpenAI
async def chat_with_open_ai():
    # Load config.json
    config = load_config()

    # OpenAI API Key
    openai.api_key = config.OpenAI.Key
    if config.OpenAI.ApiBase:
        openai.api_base = config.OpenAI.ApiBase
    gpt_model = config.OpenAI.Model

    # This example requires config.json
    speech_config = speechsdk.SpeechConfig(subscription=config.AzureCognitiveServices.Key, 
                                           region=config.AzureCognitiveServices.Region)
    audio_output_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)

    # Should be the locale for the speaker's language.
    speech_config.speech_recognition_language = config.AzureCognitiveServices.SpeechRecognitionLanguage
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    ending_punctuations = (".", "?", "!", ";")
    if (speech_config.speech_recognition_language == "zh-CN"):
        ending_punctuations = ("。", "？", "！", "；", "”")

    # The language of the voice that responds on behalf of Azure OpenAI.
    speech_config.speech_synthesis_voice_name = config.AzureCognitiveServices.SpeechSynthesisVoiceName
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_output_config)

    # The phrase your keyword recognition model triggers on.
    kws_model = speechsdk.KeywordRecognitionModel(config.AzureCognitiveServices.WakePhraseModel)
    conversation = [{"role": "system", "content": config.General.SystemPrompt}]

    while True:
        print("OpenAI is listening. Say '{}' to start.".format(config.AzureCognitiveServices.WakeWord))
        try:
            # Detect keyword
            if (not detect_keyword(kws_model, config.AzureCognitiveServices.WakeWord)):
                continue

            # Get audio from the microphone and then send it to the TTS service.
            speech_recognition_result = speech_recognizer.recognize_once_async().get()

            # If speech is recognized, send it to OpenAI and listen for the response.
            if speech_recognition_result.reason == speechsdk.ResultReason.RecognizedSpeech:
                if speech_recognition_result.text == config.AzureCognitiveServices.StopWord: 
                    print("Conversation ended.")
                    break

                print("Recognized speech: {}".format(speech_recognition_result.text))

                # Create queue for save GPT messages
                queue = asyncio.Queue()

                # Create async task for ask openai
                task_ask_gpt = asyncio.create_task(ask_openai_async(gpt_model, 
                                                                    speech_recognition_result.text, 
                                                                    config.OpenAI.MaxTokens, 
                                                                    conversation, 
                                                                    queue,
                                                                    ending_punctuations))

                # Add task done callback, add a EOF message to end
                task_ask_gpt.add_done_callback(lambda _: queue.put_nowait(EOF))

                # Create async task for Text-to-Speech
                task_ask_tts = asyncio.create_task(text_to_speech_async(speech_synthesizer, queue))

                # Wait all task completed
                await asyncio.gather(task_ask_gpt, task_ask_tts)
            elif speech_recognition_result.reason == speechsdk.ResultReason.NoMatch:
                print("No speech could be recognized: {}".format(speech_recognition_result.no_match_details))
            elif speech_recognition_result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = speech_recognition_result.cancellation_details
                print("Speech Recognition canceled: {}".format(cancellation_details.reason))
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    print("Error details: {}".format(cancellation_details.error_details))
        except EOFError:
            continue

if __name__ == '__main__':
    # Main
    try:
        asyncio.run(chat_with_open_ai())
    except Exception as err:
        print("Encountered exception. {}".format(err))