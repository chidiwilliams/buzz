window.BENCHMARK_DATA = {
  "lastUpdate": 1691183219940,
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
          "id": "64b15f1804d1923a70fdfc43bf98e30f1608278b",
          "message": "Fix Snap execstack (#537)",
          "timestamp": "2023-08-04T13:58:30-07:00",
          "tree_id": "07f5981e4b238fb31f8250c8bbdffc12dfe94a6b",
          "url": "https://github.com/chidiwilliams/buzz/commit/64b15f1804d1923a70fdfc43bf98e30f1608278b"
        },
        "date": 1691183212997,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.10966237958666694,
            "unit": "iter/sec",
            "range": "stddev: 0.05742200298012001",
            "extra": "mean: 9.118897508599957 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.04329216741405295,
            "unit": "iter/sec",
            "range": "stddev: 0.3252645767109527",
            "extra": "mean: 23.098866601799955 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}