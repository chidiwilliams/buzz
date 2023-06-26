window.BENCHMARK_DATA = {
  "lastUpdate": 1687765973940,
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
          "id": "2dc0797e64931a62a7209d0cb30913a73de949bf",
          "message": "Refactor transcribers class (#508)",
          "timestamp": "2023-06-26T07:46:17Z",
          "tree_id": "c883ebd3dea5c588703aacc50b4673f10412011e",
          "url": "https://github.com/chidiwilliams/buzz/commit/2dc0797e64931a62a7209d0cb30913a73de949bf"
        },
        "date": 1687765969948,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.06637972082105571,
            "unit": "iter/sec",
            "range": "stddev: 0.2735737828770014",
            "extra": "mean: 15.064841906999993 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.10514950554415768,
            "unit": "iter/sec",
            "range": "stddev: 0.11527060071320364",
            "extra": "mean: 9.51026821119999 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.07036048875867189,
            "unit": "iter/sec",
            "range": "stddev: 0.024932262049156228",
            "extra": "mean: 14.212522079400003 sec\nrounds: 5"
          }
        ]
      },
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
          "id": "2dc0797e64931a62a7209d0cb30913a73de949bf",
          "message": "Refactor transcribers class (#508)",
          "timestamp": "2023-06-26T07:46:17Z",
          "tree_id": "c883ebd3dea5c588703aacc50b4673f10412011e",
          "url": "https://github.com/chidiwilliams/buzz/commit/2dc0797e64931a62a7209d0cb30913a73de949bf"
        },
        "date": 1687765969948,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper.cpp - Tiny]",
            "value": 0.06637972082105571,
            "unit": "iter/sec",
            "range": "stddev: 0.2735737828770014",
            "extra": "mean: 15.064841906999993 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Whisper - Tiny]",
            "value": 0.10514950554415768,
            "unit": "iter/sec",
            "range": "stddev: 0.11527060071320364",
            "extra": "mean: 9.51026821119999 sec\nrounds: 5"
          },
          {
            "name": "tests/transcriber_benchmarks_test.py::test_should_transcribe_and_benchmark[Faster Whisper - Tiny]",
            "value": 0.07036048875867189,
            "unit": "iter/sec",
            "range": "stddev: 0.024932262049156228",
            "extra": "mean: 14.212522079400003 sec\nrounds: 5"
          }
        ]
      }
    ]
  }
}