import asyncio
import unittest
from gptspeaker import text_to_speech_async
from gptspeaker import EOF
from gptspeaker import load_config
import azure.cognitiveservices.speech as speechsdk

class TestTextToSpeechAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create a mock queue
        self.queue = asyncio.Queue()

        # Create a mock speech synthesizer
        config = load_config()
        speech_config = speechsdk.SpeechConfig(subscription=config.AzureCognitiveServices.Key, 
                                           region=config.AzureCognitiveServices.Region)
        audio_output_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_output_config)

        # Create a TextToSpeechAsync instance
        self.tts = text_to_speech_async(self.speech_synthesizer, self.queue)

    async def test_text_to_speech_async(self):
        # Test the text_to_speech_async function
        text = "Test text"

        # Put the text into the queue
        await self.queue.put(text)
        await self.queue.put(EOF)

        # 启动协程任务来运行 text_to_speech_async 函数
        task = asyncio.create_task(self.tts)

        # 等待直到队列被处理
        await task

if __name__ == '__main__':
    unittest.main()
