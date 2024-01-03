window.BENCHMARK_DATA = {
  "lastUpdate": 1704319301824,
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
          "id": "5456774d96532b5a5760d8091b2000fcef1a62c4",
          "message": "fix: snapcraft build (#656)",
          "timestamp": "2024-01-03T21:54:39Z",
          "tree_id": "72ab0197708832043adecc3e543b5b39ce1ef31f",
          "url": "https://github.com/chidiwilliams/buzz/commit/5456774d96532b5a5760d8091b2000fcef1a62c4"
        },
        "date": 1704319293771,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.09294819631682669,
            "unit": "iter/sec",
            "range": "stddev: 2.7406255934632786",
            "extra": "mean: 10.758681067799989 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.06117579837693231,
            "unit": "iter/sec",
            "range": "stddev: 4.005499321580335",
            "extra": "mean: 16.34633346079995 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}