window.BENCHMARK_DATA = {
  "lastUpdate": 1695153942455,
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
          "id": "a3b54891e8c403d28b7bf2d86443ad310d2d1b51",
          "message": "Update docs with preferences (#602)",
          "timestamp": "2023-09-19T19:53:56Z",
          "tree_id": "b14da6b2792ca95e5305f96c6f291125c7ea2813",
          "url": "https://github.com/chidiwilliams/buzz/commit/a3b54891e8c403d28b7bf2d86443ad310d2d1b51"
        },
        "date": 1695153935695,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.0963091158010936,
            "unit": "iter/sec",
            "range": "stddev: 1.4391277284738904",
            "extra": "mean: 10.38323311019999 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.04296295488967,
            "unit": "iter/sec",
            "range": "stddev: 0.6175114828270604",
            "extra": "mean: 23.275866442799998 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}