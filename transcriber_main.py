from whisper import load_model, transcribe

model = load_model('tiny')

result = transcribe(
    model=model, audio='/Users/chidiwilliams/Downloads/buzz/847787d2-236c-e7f8-d944-95b290068269.mp3', verbose=False)

print(result)
