# ChatGPT Voice Assistant
[![中文](https://img.shields.io/badge/lang-cn-yellow.svg)](https://github.com/jackwuwei/gptspeaker/blob/main/README_cn-ZH.md)
* The ChatGPT Voice Assistant uses a Raspberry Pi (or desktop) to enable spoken conversation with OpenAI large language models. This implementation listens to speech, processes the conversation through the OpenAI service, and responds back. Like Apple Siri, Amazon Alex, Google Nest Home, Mi XiaoAi etc.
* This project is written in python which supports Linux/Raspbian, macOS, and Windows.
# Features
* Supports real-time voice dialogue. After ChatGPT returns a sentence, you can hear the voice instead of waiting for all ChatGPT replies before starting the voice synthesis.
* Support continuous dialogue, save the history of all ChatGPT current conversations. When the ChatGPT conversation is larger than 4096 tokens (gpt-3.5-turbo), the early conversation history will be discarded.
* Support local wake word, use it just like Siri.
# Voice Assistant Speaker
![GPT Speaker](/image/IMG_2668.jpg "GPTSpeaker")
* Hardware
   - $ for [Raspberry PI 3/3B/4/4B](https://www.raspberrypi.com/products/)
   - $ for [USB Micro Phone](https://item.taobao.com/item.htm?spm=a230r.1.14.23.315b64e0hmblId&id=668895270969&ns=1&abbucket=1#detail)
   - $ for Aux Speaker
   - $ for an SD card (>= 8GB ) (to setup the Raspberry Pi OS)
* Software
  - [Azure Cognitive Speech Services](https://aka.ms/friendbot/azurecog)
    - **Free tier**: 5 audio hours per month and 1 concurrent request. 
    - **Free $200 credit**: With a new Azure account that can be used during the first 30 days.
  - [OpenAI](https://aka.ms/maker/openai/pricing)
    - **$0.002 / 1K tokens / ~750 words**: ChatGPT (gpt-3.5-turbo)
    - **Free $18 credit**: With a new OpenAI account that can be used during your first 90 days.
# Setup
* You will need an instance of Azure Cognitive Services and an OpenAI account. You can run the software on nearly any platform, but let's start with a Raspberry Pi.
## Raspberry Pi
* If you are new to Raspberry Pis, check out this [getting started](https://www.raspberrypi.com/documentation/computers/getting-started.html) guide.
### 1. OS
1. Insert an SD card into your PC.
1. Go to https://www.raspberrypi.com/software/ then download and run the Raspberry Pi Imager. 
1. Click `Choose OS` and select the Ubuntu 22.04.2 LTS (64-bit).
1. Click `Choose Storage`, select the SD card.
1. Click `Write` and wait for the imaging to complete.
1. Put the SD card into your Raspberry Pi and connect a keyboard, mouse, and monitor.
1. Complete the initial setup, making sure to configure Wi-Fi.
### 2. USB Speaker/Microphone
1. Plug in the USB speaker/microphone if you have not already.
1. On the Raspberry PI OS desktop, right-click on the volume icon in the top-right of the screen and make sure the USB device is selected.
1. Right-click on the microphone icon in the top-right of the screen and make sure the USB device is selected.
## Azure
The conversational speaker uses Azure Cognitive Service for speech-to-text and text-to-speech. Below are the steps to create an Azure account and an instance of Azure Cognitive Services.
### 1. Azure Account
  1. In a web browser, navigate to https://aka.ms/friendbot/azure and click on `Try Azure for Free`.
  1. Click on `Start Free` to start creating a free Azure account.
  1. Sign in with your Microsoft or GitHub account.
  1. After signing in, you will be prompted to enter some information.
        > NOTE: Even though this is a free account, Azure still requires credit card information. You will not be charged unless you change settings later.
  1. After your account setup is complete, navigate to https://aka.ms/friendbot/azureportal.

### 2. Azure Cognitive Services
  1. Sign into your account at https://aka.ms/friendbot/azureportal.
  1. In the search bar at the top, enter `Cognitive Services`. Under `Marketplace` select `Cognitive Services`. (It may take a few seconds to populate.)
  1. Verify the correct subscription is selected. Under `Resource Group` select `Create New`. Enter a resource group name (e.g. `conv-speak-rg`).
  1. Select a region and a name for your instance of Azure Cognitive Services (e.g. `my-conv-speak-cog-001`). 
        > NOTE: EastUS, WestEurope, or SoutheastAsia are recommended, as those regions tend to support the greatest number of features.  
  1. Click on `Review + Create`. After validation passes, click `Create`.
  1. When deployment has completed you can click `Go to resource` to view your Azure Cognitive Services resource.
  1. On the left side navigation bar, under `Resourse Management`, select `Keys and Endpoint`.
  1. Copy either of the two Cognitive Services keys. Save this key in a secure location for later.

  > Windows 11 users: If the application is stalling when calling the text-to-speech API, make sure you have applied all current security updates ([link](https://learn.microsoft.com/en-us/windows/release-health/resolved-issues-windows-11-22h2#2924msgdesc)).

## OpenAI
The conversational speaker uses OpenAI's models to hold a friendly conversation. Below are the steps to create a new account and access the AI models.
### 1. OpenAI Account
  1. In a web browser, navigate to https://aka.ms/maker/openai. Click `Sign up`.
        > NOTE: can use a Google account, Microsoft account, or email to create a new account.
  1. Complete the sign-up process (e.g., create a password, verify your email, etc.).
        > NOTE: If you are new to OpenAI, please review the usage guidelines (https://beta.openai.com/docs/usage-guidelines).
  1. In the top-right corner click on your account. Click on `View API keys`.
  1. Click `+ Create new secret key`. Copy the generated key and save it in a secure location for later.

  _If you are curious to play with the large language models directly, check out the https://platform.openai.com/playground?mode=chat at the top of the page after logging in to https://aka.ms/maker/openai._

# The Code
## 1. Code Configuration
1. The Python Speech SDK package is available for Windows (x64 and x86), Mac x64 (macOS X version 10.14 or later), Mac arm64 (macOS version 11.0 or later), and Linux
1. On the Raspberry Pi or your PC, open a command-line terminal.
1. On Ubuntu or Debian, run the following commands for the installation of required packages:
    ```sh
    sudo apt-get update
    sudo apt-get install libssl-dev libasound2
    ```
1. On **Ubuntu 22.04 LTS** it is also required to download and install the latest **libssl1.1** package e.g. from http://security.ubuntu.com/ubuntu/pool/main/o/openssl/.
1. Clone the repo.
   ```bash
   git clone https://github.com/jackwuwei/gptspeaker.git
   ```
1. Set your API keys: Replace config.json `{AzureCognitiveServices.Key}`and `{AzureCognitiveServices.Region}` with your OpenAI API key and `{OpenAI.Key}` with your OpenAI API key.
    ```json
    {
         "AzureCognitiveServices": {
            "Key": "AzureCognitiveServicesKey", 
            "Region": "AzureCognitiveServicesRegion",
        },

        "OpenAI": {
            "Key": "OpenAIKey", 
        }
    }
    ```
1. Run the code!
   ```bash
   pip3 install azure-cognitiveservices-speech openai tiktoken
   python3 gptspeaker.py
   ```
## 2. (Optional) Create a custom wake phrase
The code base has a default wake phrase (`"杰克同学"`) already, which I suggest you use first. If you want to create your own (free!) custom wake word, then follow the steps below.
  1. Create a custom keyword model using the directions here: https://aka.ms/hackster/microsoft/wakeword. 
  1. Download the model, extract the `.table` file and copy it to source root directory.
  1. Update `config.json` file to include your wake phrase file in the build.
     ```json
     "AzureCognitiveServices": {
        "WakePhraseModel": "xxx.table",
        "WakeWord": "xxx",
     }
     ```
  1. Rebuild and run the project to use your custom wake word.