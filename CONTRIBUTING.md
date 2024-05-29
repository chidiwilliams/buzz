# Buzz Contribution Guide

## Internationalization

To contribute a new language translation to Buzz:

1. Run `make translation_po locale=[locale]`. `[locale]` is a string with the format "language\[_script\]\[_country\]",
   where:

    - "language" is a lowercase, two-letter ISO 639 language code,
    - "script" is a titlecase, four-letter, ISO 15924 script code, and
    - "country" is an uppercase, two-letter, ISO 3166 country code.

   For example: `make translation_po locale=en_US`.

2. Fill in the translations in the `.po` file generated in `locale/[locale]/LC_MESSAGES`.
3. Run `make translation_mo` to compile the translations, then test your changes.
4. Create a new pull request with your changes.

## Troubleshooting

If you encounter any issues, please open an issue on the Buzz GitHub repository. Here are a few tips to gather data about the issue, so it is easier for us to fix.

**Provide details**

What version of the Buzz are you using? On what OS? What are steps to reproduce it? What settings were selected.

**Logs**

Log files contain valuable information about what the Buzz was doing before the issue occurred. You can get the logs like this:
* Mac and Linux run the app from the terminal and check the output.
* Windows paste this into the Windows Explorer address bar `%USERPROFILE%\AppData\Local\Buzz\Buzz\Logs` and check the logs file.

## Running Buzz locally

### Linux (Ubuntu)

1. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
2. Enter repo folder `cd buzz`
3. Install Poetry `apt-get install python3-poetry`
4. Activate the virtual environment `poetry shell`
5. Install the dependencies `poetry install`
6. Install system dependencies you may be missing 
```
sudo apt-get install --no-install-recommends libyaml-dev libegl1-mesa libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libportaudio2 gettext libpulse0
```
7. Build Buzz `poetry build`
8. Run Buzz `python -m buzz`

### Windows

1. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
2. Enter repo folder `cd buzz`
3. Install Poetry, paste this info Windows PowerShell
```
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```
4. Activate the virtual environment `poetry shell`
5. Install the dependencies `poetry install`
6. Copy `whisper.dll` from the repo backup to `buzz` folder 
```
cp .\dll_backup\whisper.dll .\buzz\
```
7. Build Buzz `poetry build`
8. Run Buzz `python -m buzz`