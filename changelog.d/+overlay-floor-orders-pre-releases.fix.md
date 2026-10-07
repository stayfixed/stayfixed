A pre-release of stayfixed no longer meets an overlay's `stayfixed.requires` floor for the release
it comes before. The floor compared the leading `X.Y.Z` alone, so a `1.0.0rc1`, `1.0.0a1` or
`1.0.0.dev0` build met `>=1.0.0`, while `stayfixed upgrade` and `doctor`'s `versions` row order
`1.0.0` after it. The session line and `doctor`'s `overlay-requires` row now say such a build does
not meet the floor, and neither does one whose suffix carries a pre-release segment anywhere, such
as `1.0.0rc1.post2` or `1.0.0.dev3+g1234abc`. A `.post1`, `.post1.dev2` or `+local` build of the
floor's version still meets it, as before.
