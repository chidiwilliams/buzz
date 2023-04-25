window.BENCHMARK_DATA = {
  "lastUpdate": 1682412714353,
  "repoUrl": "https://github.com/chidiwilliams/buzz",
  "entries": {
    "Linux": [
      {
        "commit": {
          "author": {
            "name": "chidiwilliams",
            "username": "chidiwilliams"
          },
          "committer": {
            "name": "chidiwilliams",
            "username": "chidiwilliams"
          },
          "id": "9d3d52ed2abe66e8bdeb11495d64f7f2faaf0d4f",
          "message": "Add benchmarks",
          "timestamp": "2023-04-25T08:26:59Z",
          "url": "https://github.com/chidiwilliams/buzz/pull/417/commits/9d3d52ed2abe66e8bdeb11495d64f7f2faaf0d4f"
        },
        "date": 1682412710413,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.07358081588969145,
            "unit": "iter/sec",
            "range": "stddev: 0.05378468020768506",
            "extra": "mean: 13.590498935200014 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.11460093237003174,
            "unit": "iter/sec",
            "range": "stddev: 0.0971167920591118",
            "extra": "mean: 8.725932497400004 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.10849457985541304,
            "unit": "iter/sec",
            "range": "stddev: 0.11626396793081545",
            "extra": "mean: 9.21705030180001 sec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "name": "chidiwilliams",
            "username": "chidiwilliams"
          },
          "committer": {
            "name": "chidiwilliams",
            "username": "chidiwilliams"
          },
          "id": "9d3d52ed2abe66e8bdeb11495d64f7f2faaf0d4f",
          "message": "Add benchmarks",
          "timestamp": "2023-04-25T08:26:59Z",
          "url": "https://github.com/chidiwilliams/buzz/pull/417/commits/9d3d52ed2abe66e8bdeb11495d64f7f2faaf0d4f"
        },
        "date": 1682412710413,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.07358081588969145,
            "unit": "iter/sec",
            "range": "stddev: 0.05378468020768506",
            "extra": "mean: 13.590498935200014 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.11460093237003174,
            "unit": "iter/sec",
            "range": "stddev: 0.0971167920591118",
            "extra": "mean: 8.725932497400004 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.10849457985541304,
            "unit": "iter/sec",
            "range": "stddev: 0.11626396793081545",
            "extra": "mean: 9.21705030180001 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}