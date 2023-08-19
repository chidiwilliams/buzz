window.BENCHMARK_DATA = {
  "lastUpdate": 1692409199783,
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
          "id": "f29b3aa521c1a38e24a7a292d359ce59758fd811",
          "message": "Add captions to audio player (#573)",
          "timestamp": "2023-08-19T01:29:13Z",
          "tree_id": "45071cf011d3404734b2c2c757588d53f9656ef0",
          "url": "https://github.com/chidiwilliams/buzz/commit/f29b3aa521c1a38e24a7a292d359ce59758fd811"
        },
        "date": 1692409194170,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.061045565856585916,
            "unit": "iter/sec",
            "range": "stddev: 3.6713307398825283",
            "extra": "mean: 16.381206168999984 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.04218014529562274,
            "unit": "iter/sec",
            "range": "stddev: 0.6008740156217338",
            "extra": "mean: 23.707836779399987 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}