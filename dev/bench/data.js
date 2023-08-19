window.BENCHMARK_DATA = {
  "lastUpdate": 1692408098863,
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
          "id": "f4b6b529b63b4ae1c4f411e3b3f921fa8bfd4e5a",
          "message": "Fix JSONDecodeError while reading tasks list (#572)",
          "timestamp": "2023-08-19T01:12:20Z",
          "tree_id": "f6a3cbe97a1a127326faf652a774ab01ccf898b9",
          "url": "https://github.com/chidiwilliams/buzz/commit/f4b6b529b63b4ae1c4f411e3b3f921fa8bfd4e5a"
        },
        "date": 1692408093091,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.0491192550689509,
            "unit": "iter/sec",
            "range": "stddev: 5.120466150934725",
            "extra": "mean: 20.358614938200002 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.03774916841050791,
            "unit": "iter/sec",
            "range": "stddev: 1.1035183580196386",
            "extra": "mean: 26.49064978399997 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}