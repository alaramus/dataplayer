# Paste asks about a taken name in a window

Date: 2026-09-25. Decision: D162. Revises the conflict presentation of D74
and D161.

The action menu has one Paste command. A copied file's name can already be
present at the destination, whether the two folders belong to one connection
or different ones. That conflict is a question about one attempted operation,
not a reason to add Paste variants to the menu.

When availability already reports a taken name, choosing Paste opens a window
without sending the default copy. If the destination changes after the offer,
the default copy may instead be refused; the same window then opens. It says
which name was taken and offers Cancel, Keep both, and Replace. Keep both asks
the source to find a new name; Replace explicitly permits replacing the old
file. A window keeps the original clipboard selection and destination from the
gesture that opened it, so navigating the catalog while deciding does not
silently retarget the copy. Execution still checks rights, nodes and names.

This is the same behavior for the source-owned Paste and the application-owned
cross-connection copy. The two transports remain separate, but the action
menu never teaches a person which one is behind Paste.
