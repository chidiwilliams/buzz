window.BENCHMARK_DATA = {
  "lastUpdate": 1691181067335,
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
          "id": "8b253ffc1c7eaba8f843744cb77a206a3bcc68cf",
          "message": "Add audio player (#558)",
          "timestamp": "2023-08-04T20:23:43Z",
          "tree_id": "e4eb68c8d579c68809f2adc05af0d55821794dcf",
          "url": "https://github.com/chidiwilliams/buzz/commit/8b253ffc1c7eaba8f843744cb77a206a3bcc68cf"
        },
        "date": 1691181060541,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.10395133640449636,
            "unit": "iter/sec",
            "range": "stddev: 0.4457177233799253",
            "extra": "mean: 9.619885944599991 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.0438348635985689,
            "unit": "iter/sec",
            "range": "stddev: 0.12749234998496034",
            "extra": "mean: 22.812891792200027 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}