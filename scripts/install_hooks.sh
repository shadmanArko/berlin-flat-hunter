#!/bin/sh
printf '#!/bin/sh\nexec uv run python scripts/check_no_personal_data.py\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
