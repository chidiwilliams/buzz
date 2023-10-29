window.BENCHMARK_DATA = {
  "lastUpdate": 1698597156136,
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
            "email": "williamschidi1@gmail.com",
            "name": "Chidi Williams",
            "username": "chidiwilliams"
          },
          "distinct": true,
          "id": "2567d7f65b021c467915198167025c20021115d4",
          "message": "Update docs",
          "timestamp": "2023-10-29T16:22:08Z",
          "tree_id": "90da7cc17301c0ac003013b77afcfc839443aac8",
          "url": "https://github.com/chidiwilliams/buzz/commit/2567d7f65b021c467915198167025c20021115d4"
        },
        "date": 1698597151160,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.10175572273705377,
            "unit": "iter/sec",
            "range": "stddev: 2.54990400507154",
            "extra": "mean: 9.827457101200025 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.044882309450084555,
            "unit": "iter/sec",
            "range": "stddev: 0.138047703038902",
            "extra": "mean: 22.28049341159997 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}