# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  services/codebuild.py                                ║
# ║  Little shared helper for kicking off the long-running codebuild projects.   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                                 CODEBUILD HELPERS
# ==========================================================================================
# anything that is too slow or will POTENTIALLY time out the lambda is offloaded to a 
# codebuild project. this is a shared helper to kick of those builds
# ------------------------------------------------------------------------------------------
from aws_clients import codebuild  # shared client -- made once per cold start


# ======================================START A BUILD====================================
# shared function that lets the commands kick off a codebuild project with based on the
# project name and a dict of env vars. returns True if the build was started, False if it
# failed (usually because the project doesn't exist or the lambda's IAM policy doesn't allow it)
def start_build(project, env):
    try:
        codebuild.start_build(
            projectName=project,
            # builds out the environment variables for the build
            environmentVariablesOverride=[
                {"name": name, "value": str(value)} for name, value in env.items()
            ],
        )
        return True

    except Exception as e:
        print(f"Failed to start the {project} build: {e} :(")
        return False
