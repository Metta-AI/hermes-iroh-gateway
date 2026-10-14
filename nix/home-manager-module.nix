# home-manager module for hermes-iroh-gateway.
#
# Exposed as `inputs.hermes-iroh-gateway.homeManagerModules.default` by this
# repo's flake.nix — consumers import it directly, e.g.:
#
#   inputs.hermes-iroh-gateway.url = "github:<owner>/hermes-iroh-gateway";
#   ...
#   imports = [ inputs.hermes-iroh-gateway.homeManagerModules.default ];
#
# No manual path-editing required: `self` below always resolves to wherever
# the CONSUMER's flake fetched this input from (a GitHub release, a git tag
# pin, a local `path:` override for dev) — that's what makes this portable
# across machines instead of pointing at one sandbox's absolute path.
#
# Verified inputs (not guessed — see README "Status" section for exactly
# what was and wasn't exercised):
#   - iroh 0.35.0 wheels are tagged `py3-none-<platform>` (confirmed via
#     WHEEL metadata) — ABI-agnostic across CPython versions, unlike
#     pydantic-core, so no interpreter-version matching needed.
#   - Every URL + sha256 below came straight from PyPI's JSON API
#     (https://pypi.org/pypi/iroh/0.35.0/json), not computed/guessed.
#   - fastapi (0.141.1) and uvicorn (0.51.0) confirmed present in
#     nixpkgs/nixos-unstable's python312Packages as of this writing — pulled
#     from the hermes-agent package's own python.pkgs set so they're built
#     against the exact interpreter hermes-agent-env uses (no ABI risk,
#     unlike grabbing an arbitrary wheel). Re-check these versions still
#     exist in whatever nixpkgs revision your flake pins.
#   - ONLY actually installed+imported end-to-end on x86_64-linux (that's
#     the one real Hermes process this was tested against — see README
#     "Status" for exactly what ran and what didn't). The other three
#     platform wheels are wired in from the same verified PyPI listing but
#     never exercised; flag it if one of them breaks.
{ self }:
{ config, pkgs, lib, ... }:

let
  py = config.services.hermes-agent.package.python.pkgs;

  # system -> { url, sha256 } for the iroh 0.35.0 wheel, straight from
  # https://pypi.org/pypi/iroh/0.35.0/json — only x86_64-linux verified live.
  irohWheels = {
    x86_64-linux = {
      url = "https://files.pythonhosted.org/packages/a6/01/afba5b09b5c7dbde2beee05a4e73656de4e3469f930524c15f17b96590f9/iroh-0.35.0-py3-none-manylinux_2_28_x86_64.whl";
      sha256 = "94657b606cf1aff2848cd97169f339ea145095cdf89e6aff22cfb9c868cca846";
    };
    aarch64-linux = {
      url = "https://files.pythonhosted.org/packages/76/84/523a3e6bbd77ce6de55c7452b8025be72c8daba18084a4cc28204f4b9668/iroh-0.35.0-py3-none-manylinux_2_28_aarch64.whl";
      sha256 = "c09b987c5c9e71048af236d00d3ce15c73ff0a9ed872fddf75aba8691dd9c36d";
    };
    x86_64-darwin = {
      url = "https://files.pythonhosted.org/packages/47/42/3ca27c758e491152fd402ec6e0497e889076dff8fb34f2f3991257ce593e/iroh-0.35.0-py3-none-macosx_10_12_x86_64.whl";
      sha256 = "b08f2a25b6bc34f79998c7b42ff16a26f42c4423486ea1bfe5db895a5fadaf57";
    };
    aarch64-darwin = {
      url = "https://files.pythonhosted.org/packages/72/7d/05fa04f81c9e10f7e99c13073841765fdcdbdae9c4f725dd5e0f882015bb/iroh-0.35.0-py3-none-macosx_11_0_arm64.whl";
      sha256 = "e5297b4e733a4d980b2e7d4b5dd42d3329fc87c3bb3e52c3ad40e0edb3cc0d75";
    };
  };

  irohWheel = py.buildPythonPackage {
    pname = "iroh";
    version = "0.35.0";
    format = "wheel";
    src = pkgs.fetchurl irohWheels.${pkgs.stdenv.hostPlatform.system};
    # The wheel bundles a native library needing glibc/libgcc patched in on NixOS.
    nativeBuildInputs = lib.optionals pkgs.stdenv.isLinux [ pkgs.autoPatchelfHook ];
    buildInputs = lib.optionals pkgs.stdenv.isLinux [ pkgs.stdenv.cc.cc.lib ];
    doCheck = false;
  };
in
{
  services.hermes-agent.extraPythonPackages = [
    irohWheel # fastapi/uvicorn already ship with hermes-agent
  ];

  # Directory plugin: symlinked into $HERMES_HOME/plugins/ at activation.
  # `self` is this flake's own source tree — works for GitHub, a tag, or a
  # local `path:` override, with no hardcoded absolute path.
  services.hermes-agent.extraPlugins = [
    # The derivation name matters: Hermes links it as plugins/nix-managed-<name>.
    (pkgs.runCommand "hermes-iroh-gateway" { } ''
      mkdir -p $out
      cp -r ${self}/. $out/
    '')
  ];

  services.hermes-agent.settings.plugins.enabled = [ "hermes-iroh-gateway" ];
}
