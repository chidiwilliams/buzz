window.BENCHMARK_DATA = {
  "lastUpdate": 1703327886730,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "macOS": [
      {
        "commit": {
          "author": {
            "email": "williamschidi1@gmail.com",
            "name": "Chidi Williams",
            "username": "chidiwilliams"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1120723681e3aed3646f48cba29529ebc029909e",
          "message": "fix: openai api transcriber (#652)",
          "timestamp": "2023-12-23T10:32:53Z",
          "tree_id": "97546bf0b3c5c6f6e01100626398e0e7f832292f",
          "url": "https://github.com/chidiwilliams/buzz/commit/1120723681e3aed3646f48cba29529ebc029909e"
        },
        "date": 1703327879405,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.1623878790757613,
            "unit": "iter/sec",
            "range": "stddev: 0.4248122387501858",
            "extra": "mean: 6.158095084999877 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.07872558630907954,
            "unit": "iter/sec",
            "range": "stddev: 3.2683175120141814",
            "extra": "mean: 12.702350619199752 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}