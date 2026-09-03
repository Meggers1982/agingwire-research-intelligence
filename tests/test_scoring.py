from agingwire_intel.scoring import story_score

def test_story_score():
    assert story_score(5,5,5,5,5,5,5,5) == 40
    assert story_score(5,5,5,5,5,5,5,5, penalty=7) == 33
