window.BENCHMARK_DATA = {
  "lastUpdate": 1692398538362,
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
          "id": "c498e60949e9fddd48d49355c2a05eb97407a6a7",
          "message": "Add black formatting (#571)",
          "timestamp": "2023-08-18T22:32:18Z",
          "tree_id": "b4a4dc9275123ebb976fb2cd3bbb509ffb83ea70",
          "url": "https://github.com/chidiwilliams/buzz/commit/c498e60949e9fddd48d49355c2a05eb97407a6a7"
        },
        "date": 1692398532919,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.0641513094487304,
            "unit": "iter/sec",
            "range": "stddev: 4.7024048537952",
            "extra": "mean: 15.588146346399958 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.041422408744452285,
            "unit": "iter/sec",
            "range": "stddev: 0.8058731463700783",
            "extra": "mean: 24.141522193200082 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}