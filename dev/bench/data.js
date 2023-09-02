window.BENCHMARK_DATA = {
  "lastUpdate": 1693666879214,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "macOS": [
      {
        "commit": {
          "author": {
            "email": "34811668+albanobattistella@users.noreply.github.com",
            "name": "albanobattistella",
            "username": "albanobattistella"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "775bb4a0f26e36a03b319c52883d9939164ed29a",
          "message": "Update buzz.po (#592)",
          "timestamp": "2023-09-02T14:54:03Z",
          "tree_id": "1fa7dd9d1f356bbf14f5e5d5b5ed0baf1c358861",
          "url": "https://github.com/chidiwilliams/buzz/commit/775bb4a0f26e36a03b319c52883d9939164ed29a"
        },
        "date": 1693666873386,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.13809618691652326,
            "unit": "iter/sec",
            "range": "stddev: 0.016552085306362763",
            "extra": "mean: 7.24132955680002 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.04512114830626435,
            "unit": "iter/sec",
            "range": "stddev: 0.2591970728366527",
            "extra": "mean: 22.162556529199993 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}