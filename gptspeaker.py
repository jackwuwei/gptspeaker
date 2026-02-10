#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Jack Wu. All rights reserved.
# Licensed under the BSD license. See LICENSE.md file in the project root for full license information.
"""
Smart Speaker using Azure Speech SDK and OpenAI ChatGPT API
"""
import azure.cognitiveservices.speech as speechsdk
import openai
import asyncio
import json
from collections import namedtuple
import tiktoken
import time

EOF = object()

# Load config.json
def load_config():
    try:
        with open('config.json', encoding='utf-8') as f:
            config = json.load(f, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
            if not config.AzureCognitiveServices.Key or not config.AzureCognitiveServices.Region or (not config.OpenAI.Key and not config.AzureOpenAI.Key):
                raise ValueError("Missing required configuration.")
            return config
    except FileNotFoundError:
        print("Error: config file not found.")
    except Exception as e:
        print(f"Error loading config: {e}")

# If tokens greater than max_tokens, remove oldest history messages
def truncate_conversation(conversation, max_tokens):
    """
    Truncate conversation history to fit within token limit.
    Keeps most recent messages and removes oldest ones.

    Args:
        conversation: List of message dictionaries with 'role' and 'content'
        max_tokens: Maximum tokens allowed (reserves 100 tokens for safety margin)
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    total_tokens = 0
    truncated_conversation = []

    # Iterate from newest to oldest messages
    for message in reversed(conversation):
        message_tokens = len(encoding.encode(message['content']))

        # Stop if adding this message would exceed the limit
        if total_tokens + message_tokens > max_tokens - 100:
            print(f'Token limit reached: {total_tokens + message_tokens} tokens (max: {max_tokens})')
            break

        total_tokens += message_tokens
        truncated_conversation.append(message)

    # Reverse back to chronological order and update conversation in-place
    conversation.clear()
    conversation.extend(reversed(truncated_conversation))

    print(f'Conversation truncated to {len(conversation)} messages ({total_tokens} tokens)')

# Prompts OpenAI with a request and async send sentences to queue.
async def ask_openai_async(client, model, prompt, max_token, conversation, queue, ending, config=None):
    # Append user questions
    conversation.append({"role":"user","content":prompt}) 

    # Count token limit and remove early history conversation 
    truncate_conversation(conversation, max_token)
    print(conversation)
    
    # Save one sentence
    collected_messages = ""

    # Save whole GPT answer
    full_answer = ""

    # Build API parameters
    api_params = {
        "model": model,
        "messages": conversation,
        "stream": True
    }
    
    # Add optional parameters from config if available
    if config and hasattr(config, 'OpenAI'):
        if hasattr(config.OpenAI, 'Temperature'):
            api_params["temperature"] = config.OpenAI.Temperature
        if hasattr(config.OpenAI, 'FrequencyPenalty'):
            api_params["frequency_penalty"] = config.OpenAI.FrequencyPenalty
        if hasattr(config.OpenAI, 'PresencePenalty'):
            api_params["presence_penalty"] = config.OpenAI.PresencePenalty

    # Ask OpenAI
    response = await client.chat.completions.create(**api_params)
    
    # iterate through the stream of events
    async for chunk in response:
        if not chunk.choices:
            continue

        chunk_message = chunk.choices[0].delta.content
        if not chunk_message:
            continue
        else:
            chunk_message = chunk_message.replace('\n', ' ')  # extract the message

        collected_messages += chunk_message  # save the message
        if collected_messages.endswith(ending): # One sentence
            print(f"ChatGPT Message received: {collected_messages}")
            await queue.put(collected_messages)
            full_answer += collected_messages
            collected_messages = ""

    # Save history message for continuous conversations
    conversation.append({"role":"assistant","content":full_answer})

# async read message from queue and synthesized speech
async def text_to_speech_async(speech_synthesizer, queue, rate=None):
    while True:
        text = await queue.get()
        if text is EOF:
            break

        # Use SSML for rate control if specified
        if rate:
            ssml = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US"><prosody rate="{rate}">{text}</prosody></speak>'
            speech_synthesis_result = speech_synthesizer.speak_ssml_async(ssml).get()
        else:
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
def detect_keyword(recognizer, model, keyword, audio_config):
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
    recognizer.recognized.connect(recognized_cb)
    recognizer.canceled.connect(canceled_cb)

    # Start keyword recognition.
    recognizer.start_keyword_recognition(model)
    print('Say something starting with "{}" followed by whatever you want...'.format(keyword))
    while not done:
        time.sleep(.5)

    recognizer.recognized.disconnect_all()
    recognizer.canceled.disconnect_all()
    recognizer.stop_keyword_recognition()

    # Read result audio (incl. the keyword).
    return done

def create_async_client(config):
    """Create async OpenAI Client based on configuration.
    
    Returns:
        tuple: (client, model) or (None, None) if no valid configuration found
    """
    # Create async OpenAI Client
    if hasattr(config, 'OpenAI') and config.OpenAI.Key:
        client = openai.AsyncClient(api_key=config.OpenAI.Key)
        if hasattr(config.OpenAI, 'ApiBase') and config.OpenAI.ApiBase:
            client.base_url = config.OpenAI.ApiBase
        return client, config.OpenAI.Model
    elif hasattr(config, 'AzureOpenAI') and config.AzureOpenAI.Key:
        client = openai.AsyncAzureOpenAI(api_key=config.AzureOpenAI.Key,
                                         api_version=config.AzureOpenAI.api_version,
                                         azure_endpoint=config.AzureOpenAI.Endpoint
        )
        return client, config.AzureOpenAI.Model
    else:
        print("Error: No valid OpenAI or AzureOpenAI configuration found.")
        return None, None

# Continuously listens for speech input to recognize and send as text to Azure OpenAI
async def chat_with_open_ai():
    # Load config.json
    config = load_config()
    if config is None:
        print("Failed to load configuration. Exiting.")
        return

    # Create async client
    client, gpt_model = create_async_client(config=config)
    if client is None:
        print("Failed to create OpenAI client. Exiting.")
        return

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
    
    # Initialize conversation with system prompt if available
    conversation = []
    if hasattr(config, 'General') and hasattr(config.General, 'SystemPrompt') and config.General.SystemPrompt:
        conversation.append({"role": "system", "content": config.General.SystemPrompt})
    
    # Get speech rate from config
    speech_rate = None
    if hasattr(config.AzureCognitiveServices, 'Rate'):
        speech_rate = config.AzureCognitiveServices.Rate

    while True:
        print("OpenAI is listening. Say '{}' to start.".format(config.AzureCognitiveServices.WakeWord))
        try:
            # Detect keyword
            if (not detect_keyword(speech_recognizer, kws_model, config.AzureCognitiveServices.WakeWord, audio_config)):
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
                task_ask_gpt = asyncio.create_task(ask_openai_async(client,
                                                                    gpt_model, 
                                                                    speech_recognition_result.text, 
                                                                    config.OpenAI.MaxTokens, 
                                                                    conversation, 
                                                                    queue,
                                                                    ending_punctuations,
                                                                    config))

                # Add task done callback, add a EOF message to end
                task_ask_gpt.add_done_callback(lambda _: queue.put_nowait(EOF))

                # Create async task for Text-to-Speech
                task_ask_tts = asyncio.create_task(text_to_speech_async(speech_synthesizer, queue, speech_rate))

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
