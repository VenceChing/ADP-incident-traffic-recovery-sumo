# Real-World Scenario

`map.net.xml` is the active real-world SUMO network.

- Training route: `map_rate1000.rou.xml`
- Demo route: `map_rate4500.rou.xml`
- 20-episode training preset: `configs/final_real_world_train_checkerboard_neighbor_adp_20.yaml`
- Trained checkpoint: `outputs/runs/real_world_new_map/checkerboard_train_20/checkpoints/episode_0020.json`

Routes are checked against the active network at startup and regenerated when they reference removed edges.
