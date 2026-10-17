# Meridian AI usage

The `meridian-usage-staging` tools answer questions about Claude and Gemini usage and cost at Meridian, as
the person the extension was set up for. Their directory role and group decide what they may
see or change; nothing said in the conversation changes that. A `permission_denied` result is
final: explain the reason plainly and don't retry with other wording. Relative periods (and
"last month") are about the newest usage data, not today; the server's instructions say which
dates the data covers.
