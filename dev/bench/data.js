window.BENCHMARK_DATA = {
  "lastUpdate": 1688430984797,
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
          "id": "f83d2d63d314299e5cb541ee7c6d867fb44c7818",
          "message": "Move transcriptions to individual cache files (#519)",
          "timestamp": "2023-07-04T01:28:47+01:00",
          "tree_id": "3a4f94813e4b1ac04e6e8bbf9aa2e035509afa0b",
          "url": "https://github.com/chidiwilliams/buzz/commit/f83d2d63d314299e5cb541ee7c6d867fb44c7818"
        },
        "date": 1688430981952,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.06790049665330206,
            "unit": "iter/sec",
            "range": "stddev: 0.05502264412420419",
            "extra": "mean: 14.727432777200004 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.09469776090034895,
            "unit": "iter/sec",
            "range": "stddev: 0.1913054840920357",
            "extra": "mean: 10.55991177080001 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.0691205708464677,
            "unit": "iter/sec",
            "range": "stddev: 0.2032836614229411",
            "extra": "mean: 14.467473108999991 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}