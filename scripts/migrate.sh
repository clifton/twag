#!/bin/bash
# Migrate twag data from old workspace location to XDG paths
#
# Usage:
#   ./migrate.sh /path/to/old/twitter-feed
#
# This will copy:
#   - twag.db → ~/.local/share/twag/twag.db
#   - following.txt → ~/.local/share/twag/following.txt
#   - *.md digests → ~/.local/share/twag/digests/

set -e

OLD_DIR="${1:?Usage: $0 /path/to/old/twitter-feed}"

# Determine target directory
if [ -n "$TWAG_DATA_DIR" ]; then
    NEW_DIR="$TWAG_DATA_DIR"
elif [ -n "$XDG_DATA_HOME" ]; then
    NEW_DIR="$XDG_DATA_HOME/twag"
else
    NEW_DIR="$HOME/.local/share/twag"
fi

echo "Migrating twag data..."
echo "  From: $OLD_DIR"
echo "  To:   $NEW_DIR"
echo ""

# Validate source directory
if [ ! -d "$OLD_DIR" ]; then
    echo "ERROR: Source directory does not exist: $OLD_DIR"
    exit 1
fi

# Create target directories
mkdir -p "$NEW_DIR/digests"

# Migrate database
if [ -f "$OLD_DIR/twag.db" ]; then
    if [ -f "$NEW_DIR/twag.db" ]; then
        echo "WARNING: Database already exists at target. Skipping."
        echo "  To force: rm $NEW_DIR/twag.db && re-run"
    else
        cp "$OLD_DIR/twag.db" "$NEW_DIR/twag.db"
        echo "[OK] Migrated twag.db"
    fi
else
    echo "[SKIP] No twag.db found in source"
fi

# Migrate following.txt
if [ -f "$OLD_DIR/following.txt" ]; then
    if [ -f "$NEW_DIR/following.txt" ]; then
        echo "WARNING: following.txt already exists at target. Skipping."
    else
        cp "$OLD_DIR/following.txt" "$NEW_DIR/following.txt"
        echo "[OK] Migrated following.txt"
    fi
else
    echo "[SKIP] No following.txt found in source"
fi

# Migrate seen.json (for later migration via twag db migrate-seen)
if [ -f "$OLD_DIR/seen.json" ]; then
    if [ -f "$NEW_DIR/seen.json" ]; then
        echo "WARNING: seen.json already exists at target. Skipping."
    else
        cp "$OLD_DIR/seen.json" "$NEW_DIR/seen.json"
        echo "[OK] Migrated seen.json (run 'twag db migrate-seen' to import)"
    fi
fi

# Migrate digest files (*.md)
DIGEST_COUNT=0
for md_file in "$OLD_DIR"/*.md; do
    [ -f "$md_file" ] || continue
    filename=$(basename "$md_file")

    # Skip non-date files
    if [[ ! "$filename" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$ ]]; then
        continue
    fi

    if [ -f "$NEW_DIR/digests/$filename" ]; then
        continue  # Skip existing
    fi

    cp "$md_file" "$NEW_DIR/digests/$filename"
    ((DIGEST_COUNT++))
done

if [ $DIGEST_COUNT -gt 0 ]; then
    echo "[OK] Migrated $DIGEST_COUNT digest files"
else
    echo "[SKIP] No new digest files to migrate"
fi

echo ""
echo "Migration complete!"
echo ""
echo "Next steps:"
echo "  1. Verify data: twag stats"
echo "  2. Test fetch: twag fetch --no-tier1"
echo "  3. If everything works, you can archive the old directory:"
echo "     mv $OLD_DIR $OLD_DIR.bak"
