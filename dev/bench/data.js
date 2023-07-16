window.BENCHMARK_DATA = {
  "lastUpdate": 1689494398391,
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
          "id": "f0c3c054b86ce13e89eb20275e9107f965ef7d6c",
          "message": "Delete stale.yml",
          "timestamp": "2023-07-16T08:52:27+01:00",
          "tree_id": "3f691caf3e0d18692d5fb5510bdf3ac3ec724bf7",
          "url": "https://github.com/chidiwilliams/buzz/commit/f0c3c054b86ce13e89eb20275e9107f965ef7d6c"
        },
        "date": 1689494391819,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.11037179261417102,
            "unit": "iter/sec",
            "range": "stddev: 0.05115135234655725",
            "extra": "mean: 9.060285932799161 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.046348973902003404,
            "unit": "iter/sec",
            "range": "stddev: 0.06296566758862049",
            "extra": "mean: 21.57545066940038 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}