# Third-party protocol code

`bmd.py` and `speed-editor-demo.py` are unchanged copies from
https://github.com/smunaut/blackmagic-misc (retrieved 2026-10-26).
Copyright (C) 2021 Sylvain Munaut <tnt@246tNt.com>, Apache-2.0.
The full license is included in LICENSE-Apache-2.0.txt.

`speededitor/bmd_protocol.py` contains their key/LED enums and authentication
algorithm, with the unused `hid` import and device interface removed.
`speededitor/device.py` adapts their handshake to Linux hidraw and the Windows
HIDAPI transport in `speededitor/windows_hid.py`.
No claim is made to having reverse engineered this protocol.

Driver behavior reference: https://github.com/davidgiven/bmdkey
Resolve shortcut reference: Blackmagic Design's Editor's Guide:
https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Editors-Guide.pdf
The Resolve preset needs validation against the user's installed shortcut layout.
