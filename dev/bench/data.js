window.BENCHMARK_DATA = {
  "lastUpdate": 1687281580631,
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
          "id": "798d623a386a123c3c3ac1f0419af6e1f19c40e4",
          "message": "Fix brew cask deployment (#502)",
          "timestamp": "2023-06-20T17:12:51Z",
          "tree_id": "a67d4cba3a84c67bbe6c034ff1cb6eaa82b8d3b4",
          "url": "https://github.com/chidiwilliams/buzz/commit/798d623a386a123c3c3ac1f0419af6e1f19c40e4"
        },
        "date": 1687281576070,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.06116000821237365,
            "unit": "iter/sec",
            "range": "stddev: 0.2527193614029132",
            "extra": "mean: 16.35055372339999 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.09899164153292549,
            "unit": "iter/sec",
            "range": "stddev: 0.28933328368205596",
            "extra": "mean: 10.101862990799997 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.09740036010494181,
            "unit": "iter/sec",
            "range": "stddev: 0.17857445699448563",
            "extra": "mean: 10.26690249319995 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}