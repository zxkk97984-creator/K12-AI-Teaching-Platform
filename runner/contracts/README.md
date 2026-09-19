# Code task contracts

`code-task.schema.json` is the versioned task-definition contract. It contains
the student-visible starter, examples, public input/output shape, and public
test-group summaries. It deliberately contains no reference implementation,
hidden case input, hidden expected output, or pytest source.

`grading-result.schema.json` is the result contract emitted by the trusted
grader after a runner has returned structured observations. A student's
stdout, claimed pass count, or claimed JSON result is not an input to the
trusted score. `SYSTEM_ERROR` and `NOT_VERIFIED` carry a null score rather
than silently becoming a student zero.

The actual reference/oracle implementation stays on the trusted backend side
until the isolated runner work in T24 defines the process boundary. These
schemas are not evidence that a real Docker runner is already available.
