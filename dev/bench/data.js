window.BENCHMARK_DATA = {
  "lastUpdate": 1687513822019,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "Linux": [
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
          "id": "fa08e5344e7b400b4afd10c692dbaedea1aba2c8",
          "message": "Add installation docs (#506)",
          "timestamp": "2023-06-23T10:43:29+01:00",
          "tree_id": "e365c9157f4a2faf7a94e03b81771991fd3a873a",
          "url": "https://github.com/chidiwilliams/buzz/commit/fa08e5344e7b400b4afd10c692dbaedea1aba2c8"
        },
        "date": 1687513818003,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.0681824734497892,
            "unit": "iter/sec",
            "range": "stddev: 0.11818191888828515",
            "extra": "mean: 14.666525712599997 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.10147059101084308,
            "unit": "iter/sec",
            "range": "stddev: 0.2563376439768121",
            "extra": "mean: 9.8550721942 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.07147655638148574,
            "unit": "iter/sec",
            "range": "stddev: 0.054485195302757576",
            "extra": "mean: 13.990601263199995 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}