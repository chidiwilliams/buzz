window.BENCHMARK_DATA = {
  "lastUpdate": 1703119018269,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "macOS": [
      {
        "commit": {
          "author": {
            "email": "fitojb@ubuntu.com",
            "name": "Adolfo Jayme-Barrientos",
            "username": "fitojb"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "68207970b1767cb9e8bc7278e30f8645f5e32f67",
          "message": "Update Spanish translation (#628)",
          "timestamp": "2023-11-09T19:41:06Z",
          "tree_id": "01b4d4136f0a4682ce776c88263f0c8344cbbceb",
          "url": "https://github.com/chidiwilliams/buzz/commit/68207970b1767cb9e8bc7278e30f8645f5e32f67"
        },
        "date": 1703119012707,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.06301370295422343,
            "unit": "iter/sec",
            "range": "stddev: 1.9817152262176214",
            "extra": "mean: 15.869564128400043 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.07896507842997161,
            "unit": "iter/sec",
            "range": "stddev: 1.563882872125196",
            "extra": "mean: 12.663825831399981 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}