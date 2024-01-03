window.BENCHMARK_DATA = {
  "lastUpdate": 1704317130205,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "macOS": [
      {
        "commit": {
          "author": {
            "email": "sebek@life.pl",
            "name": "Sebastian",
            "username": "Sebek05"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c758a25a4190dbd6c33867140bb386fb2fd6dbfa",
          "message": "Update buzz.po (#658)",
          "timestamp": "2024-01-03T21:20:15Z",
          "tree_id": "1a0329ec558da6b49e0a07ceebd90dab34b1951c",
          "url": "https://github.com/chidiwilliams/buzz/commit/c758a25a4190dbd6c33867140bb386fb2fd6dbfa"
        },
        "date": 1704317122903,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.15331122424727972,
            "unit": "iter/sec",
            "range": "stddev: 0.7152424266835279",
            "extra": "mean: 6.5226796335999095 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.08773785565791442,
            "unit": "iter/sec",
            "range": "stddev: 0.054141784232723325",
            "extra": "mean: 11.397588788800022 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}