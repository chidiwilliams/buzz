from buzz.transformers_whisper import load_model


class TestTransformersWhisper:
    def test_should_transcribe(self):
        model = load_model('openai/whisper-tiny')
        result = model.transcribe(
            audio_path='testdata/whisper-french.mp3', language='fr', task='transcribe')

        assert 'Bienvenue dans Passe' in result['text']
