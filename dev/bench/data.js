window.BENCHMARK_DATA = {
  "lastUpdate": 1699522238939,
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
          "id": "43aa719fa405699a6607526a10fc0e4c2f1deafe",
          "message": "Upgrade to Whisper v3 (#626)",
          "timestamp": "2023-11-09T09:20:38Z",
          "tree_id": "1bedbdae8862dcd641519f9b690f89309f38e307",
          "url": "https://github.com/chidiwilliams/buzz/commit/43aa719fa405699a6607526a10fc0e4c2f1deafe"
        },
        "date": 1699522231008,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.060746087559675074,
            "unit": "iter/sec",
            "range": "stddev: 8.234074555173287",
            "extra": "mean: 16.4619655384 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.07019148713180727,
            "unit": "iter/sec",
            "range": "stddev: 2.1670829621646828",
            "extra": "mean: 14.246741889400004 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}