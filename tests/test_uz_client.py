from uz_watcher.uz_client import extract_seat_summary


def test_extract_seat_summary_sums_wagon_classes():
    trips = [
        {
            "train": {
                "number": "089К",
                "wagon_classes": [
                    {"name": "Купе", "free_seats": 10},
                    {"name": "Плацкарт", "free_seats": 5},
                ],
            },
            "depart_at": 1782000000,
            "arrive_at": 1782040000,
        }
    ]

    summary = extract_seat_summary(trips)

    assert len(summary) == 1
    trip = summary[0]
    assert trip["train_number"] == "089К"
    assert trip["free_seats"] == 15
    assert trip["wagon_classes"] == [
        {"name": "Купе", "free_seats": 10},
        {"name": "Плацкарт", "free_seats": 5},
    ]


def test_extract_seat_summary_omits_full_wagon_classes():
    trips = [
        {
            "train": {
                "number": "070О",
                "wagon_classes": [
                    {"name": "Купе", "free_seats": 0},
                    {"name": "Плацкарт", "free_seats": 3},
                ],
            },
            "depart_at": 1782000000,
            "arrive_at": 1782040000,
        }
    ]

    summary = extract_seat_summary(trips)

    assert summary[0]["free_seats"] == 3
    assert summary[0]["wagon_classes"] == [{"name": "Плацкарт", "free_seats": 3}]


def test_extract_seat_summary_handles_missing_train_number():
    trips = [{"train": {"wagon_classes": []}, "depart_at": None, "arrive_at": None}]

    summary = extract_seat_summary(trips)

    assert summary[0]["train_number"] == "?"
    assert summary[0]["departure"] == "?"
    assert summary[0]["arrival"] == "?"
    assert summary[0]["free_seats"] == 0
