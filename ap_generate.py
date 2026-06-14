#!/home/stubob/.pyenv/versions/3.13.13/bin/python3
"""Generate an Archipelago multidata file for One Must Fall: 2097."""
import sys
import os
import zipfile
import argparse

AP_DIR = os.path.join(os.path.dirname(__file__), "archipelago")
sys.path.insert(0, AP_DIR)

# Patch version check before importing ModuleUpdate — AP caps at 3.13 but 3.14 works fine.
import types
_mu_path = os.path.join(AP_DIR, "ModuleUpdate.py")
_mu_src = open(_mu_path).read().replace("(3, 14, 0)", "(3, 99, 0)")
_mu = types.ModuleType("ModuleUpdate")
_mu.__file__ = _mu_path
exec(compile(_mu_src, _mu_path, "exec"), _mu.__dict__)
sys.modules["ModuleUpdate"] = _mu
import ModuleUpdate; ModuleUpdate.update = lambda: None  # noqa: E402

def main():
    p = argparse.ArgumentParser()
    p.add_argument("slot", nargs="?", default="player")
    p.add_argument("--out", default="/tmp/omf_output")
    p.add_argument("--players-dir", default="/tmp/omf_players")
    p.add_argument("--goal", default="world_championship",
                   choices=["north_american_open","katushai_challenge","war_invitational",
                            "world_championship","all_tournaments"])
    p.add_argument("--starting-har", default="random_selection")
    p.add_argument("--har-stat-max", type=int, default=9)
    p.add_argument("--pilot-stat-max", type=int, default=25)
    p.add_argument("--buy-cost-factor", type=int, default=100)
    p.add_argument("--no-buy", action="store_true")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.players_dir, exist_ok=True)

    yaml_path = os.path.join(args.players_dir, f"{args.slot}.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"""\
name: {args.slot}
game: "One Must Fall: 2097"

"One Must Fall: 2097":
  goal_tournament: {args.goal}
  starting_har: {args.starting_har}
  har_stat_max: {args.har_stat_max}
  pilot_stat_max: {args.pilot_stat_max}
  include_buy_locations: {"false" if args.no_buy else "true"}
  buy_cost_factor: {args.buy_cost_factor}
""")
    print(f"Wrote {yaml_path}")

    sys.argv = ["Generate.py", "--player_files_path", args.players_dir, "--outputpath", args.out]
    import Generate
    erargs, seed = Generate.main()
    from Main import main as ERmain
    ERmain(erargs, seed)

    # Find and report the zip
    zips = sorted(
        [f for f in os.listdir(args.out) if f.startswith("AP_") and f.endswith(".zip")],
        key=lambda f: os.path.getmtime(os.path.join(args.out, f)),
        reverse=True,
    )
    if not zips:
        print("ERROR: no AP_*.zip found", file=sys.stderr)
        sys.exit(1)

    zippath = os.path.join(args.out, zips[0])
    with zipfile.ZipFile(zippath) as zf:
        for name in zf.namelist():
            if name.endswith(".archipelago"):
                dest = os.path.join(args.out, name)
                if not os.path.exists(dest):
                    zf.extract(name, args.out)
                print(dest)
                return
    print("ERROR: no .archipelago inside zip", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
