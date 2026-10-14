`stayfixed attach` now says when it withdrew harness memory links, the links through which Claude
Code reads a project's notes, and why. When the store had been approved and then changed, one line
appended to one note being enough, the run withdrew the link from every checkout and said only that
the link "has no approval yet", which reads as a store nobody approved, and nothing of what it
removed. The line now counts the links it withdrew whenever it withdrew any, and says the store or
its `memory.index_extra` changed since its approval was recorded; a store never approved is still
told it has no approval yet. What is withdrawn is unchanged.
