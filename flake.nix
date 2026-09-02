# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  NIX  ::  flake.nix                                                          ║
# ║  The dev shell -- every tool ci-all.yaml runs, and nothing installed         ║
# ║  globally. flake.lock pins the exact versions, so the shell you get today    ║
# ║  is the shell you get in six months :)                                       ║
# ║                                                                              ║
# ║  `direnv allow` once and it loads whenever you cd in. no direnv? then         ║
# ║  `nix develop` gets you the identical shell by hand.                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
{
  description = "CraftForm -- discord-driven minecraft server infrastructure";

  inputs = {
    # unstable on purpose -- ruff/cfn-lint/checkov move fast, and the stable channel
    # lags far enough behind to start disagreeing with what CI pip-installs
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      # linux for this box + actions, darwin so a mac can work on it too
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];

      # tiny stand-in for flake-utils -- not worth a second input for one function
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs {
        inherit system;

        config = {
          # terraform went BUSL back at 1.6, so nixpkgs flags it unfree and refuses
          # to build it. allow that ONE package by name instead of flipping
          # allowUnfree for the whole shell -- keeps the blast radius to the thing
          # we actually need
          allowUnfreePredicate = pkg:
            builtins.elem (nixpkgs.lib.getName pkg) [ "terraform" ];

          # checkov transitively pulls the pure-python ecdsa lib, which nixpkgs
          # flags for CVE-2024-23342 -- the "Minerva" timing side-channel on ecdsa
          # signing. checkov never signs anything, it reads our terraform and yaml
          # off the disk, and nobody's positioned to time it. so: noise, for us.
          #
          # pinned to the EXACT version on purpose. when a nixpkgs bump moves it,
          # this stops working and you get to re-read the paragraph above instead
          # of silently inheriting whatever the new insecure package turns out to be
          permittedInsecurePackages = [ "python3.14-ecdsa-0.19.2" ];
        };
      }));
    in
    {
      devShells = forAllSystems (pkgs:
        let
          # ====================================================================
          #                              PYTHON
          # ====================================================================
          # mirrors lambda/*/requirements-dev.txt with cfn-lint bolted on. ONE
          # interpreter for the whole repo, so mypy sees exactly the stubs the
          # rest of the tooling does
          python = pkgs.python312.withPackages (ps: [
            ps.cfn-lint     # the ci gate on cloudformation/*.yaml
            ps.mypy         # type check
            ps.bandit       # python security scan
            ps.pynacl       # operations lambda -- verifies discord's ed25519 sigs
            ps.urllib3      # both lambdas -- the discord + cloudformation http calls
            ps.boto3-stubs  # what lets mypy understand the boto3 client calls
          ] ++ ps.boto3-stubs.optional-dependencies.essential); # the [essential] extra

          # ====================================================================
          #                            THE CI RUNNER
          # ====================================================================
          # runs what .github/workflows/ci-all.yaml runs, in the same order, so you
          # find out here instead of three minutes into a pushed run :)
          ci = pkgs.writeShellScriptBin "ci" ''
            # deliberately NO -e -- every check should run even after one fails, so
            # you get the whole picture in one go rather than one problem at a time
            set -uo pipefail

            ROOT="$(git rev-parse --show-toplevel)" || exit 1
            FAILED=()

            step() {
              # grab the label BEFORE the shift -- after it, $1 is the command
              local label="$1"; shift
              printf '\n\033[1;34m==> %s\033[0m\n' "$label"
              if "$@"; then
                printf '\033[0;32m    ok :)\033[0m\n'
              else
                printf '\033[0;31m    FAILED :(\033[0m\n'
                FAILED+=("$label")
              fi
            }

            # ---- cloudformation ----
            cfn() { cfn-lint "$ROOT"/cloudformation/*.yaml; }

            # ---- terraform ---- (subshells so the cd doesn't leak into the next step)
            tf_fmt()  { ( cd "$ROOT/terraform" && terraform fmt -check -recursive ); }
            tf_val()  { ( cd "$ROOT/terraform" \
                          && terraform init -backend=false -input=false >/dev/null \
                          && terraform validate ); }
            tf_lint() { ( cd "$ROOT/terraform" \
                          && tflint --init >/dev/null \
                          && tflint --recursive --format compact ); }

            # ---- the lambdas ---- (matches the startup/operations matrix)
            py() { ( cd "$ROOT/lambda/$1" \
                     && ruff format --diff . \
                     && ruff check . \
                     && mypy . \
                     && bandit -r . -ll ); }

            # ---- security ----
            # the action scans history, so we do too. `git` replaced `detect` in
            # gitleaks 8.x -- fall back so an older binary still works
            leaks() {
              if gitleaks git --help >/dev/null 2>&1; then
                gitleaks git "$ROOT" --no-banner
              else
                gitleaks detect --source "$ROOT" --no-banner
              fi
            }
            iac() { ( cd "$ROOT" && checkov --config-file .checkov.yaml ); }

            step "cloudformation lint"  cfn
            step "terraform fmt"        tf_fmt
            step "terraform validate"   tf_val
            step "tflint"               tf_lint
            step "lambda: startup"      py startup
            step "lambda: operations"   py operations
            step "gitleaks"             leaks
            step "checkov"              iac

            echo ""
            if [ ''${#FAILED[@]} -eq 0 ]; then
              printf '\033[0;32mall checks passed :)\033[0m\n'
            else
              printf '\033[0;31m%s check(s) failed:\033[0m %s\n' "''${#FAILED[@]}" "''${FAILED[*]}"
              exit 1
            fi
          '';
        in
        {
          default = pkgs.mkShell {
            name = "craftform";

            packages = [
              python
              ci

              # ==================== IAC ====================
              pkgs.terraform  # the region deploys -- buildspec.yaml pins its own copy
              pkgs.tflint     # configured by terraform/.tflint.hcl
              pkgs.checkov    # configured by .checkov.yaml

              # ================= PYTHON TOOLING ==============
              pkgs.ruff       # format + lint. the standalone binary, same as pip's

              # ================ EVERYTHING ELSE ==============
              pkgs.gitleaks   # the secret scan ci runs on every push
              pkgs.awscli2    # poking at the deployed stack by hand
              pkgs.jq         # the buildspec builds its discord json with this
              pkgs.zip        # the release workflow's zips, for testing them locally
              pkgs.unzip
            ];

            # mypy writes .mypy_cache wherever it runs -- already gitignored, but this
            # keeps the two lambda dirs from fighting over one cache
            MYPY_CACHE_DIR = ".mypy_cache";

            shellHook = ''
              # checkov and awscli2 are built against python 3.14, and mkShell helpfully
              # stacks every one of their deps onto PYTHONPATH. our own tooling is 3.12,
              # so cfn-lint would start up, find the 3.14 copy of `regex` first, and die
              # importing a C extension built for the wrong ABI.
              #
              # nothing here actually wants PYTHONPATH: checkov/aws are wrapped binaries
              # that set their own, and python312.withPackages puts our packages on the
              # interpreter's real sys.path. so drop it and let each tool use its own :)
              unset PYTHONPATH

              echo ""
              echo "  CraftForm  ::  dev shell"
              echo "  ---------------------------------------------"
              echo "  ci    run every check ci-all.yaml runs"
              echo ""
            '';
          };
        });
    };
}
