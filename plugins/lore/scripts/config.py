"""Capability flags for the lore plugin.

Each flag represents an optional capability that may be deferred or
conditionally enabled. Flip a flag here to activate or suppress the
corresponding behavior across the plugin.
"""

# Mid-conversation recall via UserPromptSubmit classification.
# When False, lore's SessionStart banner announces that area recall
# is available at session start only, not during conversation turns.
# Flip this to True when the UserPromptSubmit classifier is ported.
RECALL_CLASSIFIER_ENABLED: bool = False

# Install-state-gated clickable links in the SessionStart banner.
# When False, force plain vault-relative paths in the banner even when the
# link server is installed (install-state file present). Use this as a
# kill-switch if the link server is broken or disabled mid-session.
LINK_SERVER_ENABLED: bool = True
