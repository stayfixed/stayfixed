`stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now read a backticked path's
symbol suffix, such as `::parser::parse`, without keeping a record for each of its parts. A line
whose suffix had a million parts took 150 MiB more memory to read, and a document as long as a
reader takes could ask gigabytes. The same spans are read as paths as before.
