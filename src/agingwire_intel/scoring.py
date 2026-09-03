def story_score(novelty:int, impact:int, localization:int, consumer_utility:int,
                b2b_relevance:int, visualization:int, timeliness:int,
                original_analysis:int, penalty:int=0) -> int:
    values = [novelty, impact, localization, consumer_utility, b2b_relevance,
              visualization, timeliness, original_analysis]
    if any(v < 0 or v > 5 for v in values):
        raise ValueError("Each component must be 0-5")
    return max(0, sum(values) - penalty)
