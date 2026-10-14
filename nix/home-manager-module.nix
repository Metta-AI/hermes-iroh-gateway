# home-manager module snippet for hermes-iroh-gateway
#
# This is NOT evaluated by this repo's own flake.nix (that one is just the
# dev shell for building/testing the plugin in isolation). This file is the
# deliverable for the OTHER side: paste/import it into your nixos-config /
# home-manager repo, wherever `services.hermes-agent` is already configured.
#
# Verified inputs (not guessed):
#   - iroh 0.35.0 wheel tag is `py3-none-<platform>` (confirmed via WHEEL
#     metadata) — ABI-agnostic across CPython versions, so no interpreter
#     version matching needed, unlike pydantic-core.
#   - sha256 digests below came straight from PyPI's JSON API
#     (https://pypi.org/pypi/iroh/0.35.0/json), not computed/guessed locally.
#   - fastapi (0.141.1) and uvicorn (0.51.0) confirmed present in
#     nixpkgs/nixos-unstable's python312Packages — pulled from the
#     hermes-agent package's own python.pkgs set so they're built against
#     the exact same interpreter as hermes-agent-env (no ABI risk, unlike a
#     wheel grab).
#
# Adjust `system` below if your machine isn't x86_64-linux (aarch64-linux /
# x86_64-darwin / aarch64-darwin wheel hashes are in the comment block).
{ config, pkgs, lib, ... }:

let
  py = config.services.hermes-agent.package.python.pkgs;

  irohWheel = py.buildPythonPackage {
    pname = "iroh";
    version = "0.35.0";
    format = "wheel";
    src = pkgs.fetchurl {
      # x86_64-linux (glibc). Other platforms, same PyPI release:
      #   macosx_10_12_x86_64:     sha256 b08f2a25b6bc34f79998c7b42ff16a26f42c4423486ea1bfe5db895a5fadaf57
      #   macosx_11_0_arm64:       sha256 e5297b4e733a4d980b2e7d4b5dd42d3329fc87c3bb3e52c3ad40e0edb3cc0d75
      #   manylinux_2_28_aarch64:  sha256 c09b987c5c9e71048af236d00d3ce15c73ff0a9ed872fddf75aba8691dd9c36d
      #   win_amd64:               sha256 e18fb474fa1ff9ae9c1b8bf4bc53d68ab636d5d1be852a57080bcbf6e9d58d92
      url = "https://files.pythonhosted.org/packages/a6/01/afba5b09b5c7dbde2beee05a4e73656de4e3469f930524c15f17b96590f9/iroh-0.35.0-py3-none-manylinux_2_28_x86_64.whl";
      sha256 = "94657b606cf1aff2848cd97169f339ea145095cdf89e6aff22cfb9c868cca846";
    };
    # Wheel install only — nothing to build.
    dontBuild = true;
    pyproject = false;
  };
in
{
  services.hermes-agent.extraPythonPackages = [
    irohWheel
    py.fastapi
    py.uvicorn
  ];

  # Directory plugin: symlinked into $HERMES_HOME/plugins/ at activation.
  # Point this at wherever you keep the checkout, or fetchFromGitHub once
  # it's pushed to a remote.
  services.hermes-agent.extraPlugins = [
    (pkgs.runCommand "hermes-iroh-gateway-plugin" { } ''
      mkdir -p $out
      cp -r ${/home/malcolm/Projects/softmax/hermes-iroh-gateway}/* $out/
    '')
  ];

  services.hermes-agent.settings.plugins.enabled = [ "hermes-iroh-gateway" ];
}
