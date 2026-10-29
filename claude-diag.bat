@echo off
cd /d "%~dp0"
(
echo === branch ===
git branch -a
echo === remote ===
git remote -v
echo === log ===
git log --oneline -5
echo === user ===
git config user.name
git config user.email
echo === fetch ===
git fetch origin
git status -sb
echo === status ===
git status --short
echo === tracked ===
git ls-files
echo === fim ===
) > ".git\claude-diag.log" 2>&1
