from scene_plan import upgrade


def test_no_two_scenes_in_a_row_share_media():
    data = {"verses": [{"narration": [
        "개역개정은 이렇게 적어요.",             # scroll
        "개역개정은 그 말을 지웠어요.",          # scroll again → must switch
        "아무 키워드 없는 문장.",                 # default
        "역시 키워드 없는 문장.",                 # default again → must switch
    ]}]}
    media = [s["media"] for s in upgrade(data)["verses"][0]["scenes"]]
    assert media[0] == "bg/video/ancient_scroll.mp4"
    assert all(a != b for a, b in zip(media, media[1:])), media
