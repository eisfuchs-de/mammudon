# Mammudon

Mammudon strives to be a user-friendly desktop Mastodon client. It was written
in Python using the Qt Version 6 user interface toolkit.

[The source for this project is available here][src].

## Install dependencies

- Mastodon.py
- python311-PyQt6
- python311-ffmpeg-python  - !NOTE! Do not install "python-ffmpeg" or just "ffmpeg", it has to be "ffmpeg-python"
- python311-PyQt6-WebEngine
- qt6-multimedia

## Installation

Install me without building it yourself (TODO):

```bash
pip install mammudon # TODO - not yet available
```

## Usage
```bash
mammudon
```

## Building

Build me from source with:

```bash
python -m build
python -m install
```

----

[src]: https://github.com/eisfuchs-de/mammudon
