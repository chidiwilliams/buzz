window.BENCHMARK_DATA = {
  "lastUpdate": 1688507927936,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "Linux": [
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
          "id": "59d9dc224318e0ea6f336ddf1a6afcda1dd59de7",
          "message": "Fix Faster Whisper large model selection (#523)",
          "timestamp": "2023-07-04T21:52:45Z",
          "tree_id": "76600f4e77363d262ac1d18a7d34c1f6aff8f6be",
          "url": "https://github.com/chidiwilliams/buzz/commit/59d9dc224318e0ea6f336ddf1a6afcda1dd59de7"
        },
        "date": 1688507924892,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.07634860500137056,
            "unit": "iter/sec",
            "range": "stddev: 0.1614543125110439",
            "extra": "mean: 13.097816259800016 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.11871638649600944,
            "unit": "iter/sec",
            "range": "stddev: 0.06833136452311307",
            "extra": "mean: 8.423436978800009 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.07428537794682243,
            "unit": "iter/sec",
            "range": "stddev: 0.09732181650581044",
            "extra": "mean: 13.4615994108 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}