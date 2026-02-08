# Contributing to Bare-Metal Forth

## Before You Start

Please read [MANIFESTO.md](MANIFESTO.md). This isn't a typical open source project, and we're not looking for typical contributions.

We value:
- Quality over quantity
- Understanding over speed
- Reliability over features

## Types of Contributions

### What We Welcome

1. **Bug fixes** with clear explanations of what was wrong and why the fix is correct
2. **Documentation improvements** that make the system more understandable
3. **Test cases** that verify correct behavior, especially edge cases
4. **Performance improvements** that don't sacrifice clarity
5. **Forth-83 compliance** fixes with references to the standard

### What We Don't Want

1. Features that add complexity without clear benefit
2. "Drive-by" PRs without discussion
3. Code that the submitter doesn't fully understand
4. Dependencies on external libraries
5. Platform-specific hacks that compromise portability

## Process

### 1. Discuss First

Before writing code, open an issue to discuss:
- What problem are you solving?
- Why does it need solving?
- What approach do you propose?
- What are the tradeoffs?

We may say no. That's not personal—it's about maintaining focus.

### 2. Write the Code

If we agree the work should proceed:

```bash
# Fork the repository
# Create a feature branch
git checkout -b your-feature-name

# Make your changes
# Test thoroughly
make test

# Commit with clear messages
git commit -m "Brief summary

Longer explanation of what and why.
Reference any issues: Fixes #123"
```

### 3. Submit for Review

- Open a pull request against `main`
- Fill out the PR template completely
- Be prepared to iterate based on feedback
- Don't take feedback personally

### 4. Code Review Standards

Every PR will be reviewed for:

| Criterion | Question |
|-----------|----------|
| Correctness | Does it work? Does it handle edge cases? |
| Clarity | Can someone unfamiliar understand it? |
| Simplicity | Is there a simpler way? |
| Consistency | Does it match existing style? |
| Testing | Is it adequately tested? |
| Documentation | Is it documented? |

## Code Style

### Assembly (NASM)

```nasm
; ============================================================================
; Section headers like this
; ============================================================================

; Comments explain WHY, not WHAT
; Bad:  mov eax, 5      ; move 5 into eax
; Good: mov eax, 5      ; syscall number for open()

DEFWORD "EXAMPLE", 7, EXAMPLE, 0    ; Name, length, label, flags
    ; Implementation
    NEXT

; Align data to natural boundaries
section .data
    align 4
    my_variable: dd 0
```

### Forth

```forth
\ Document each word
\ ( stack-before -- stack-after )  description

: SQUARE  ( n -- n^2 )
    DUP *
;

\ Use vertical alignment for clarity in complex definitions
: COMPLEX-WORD  ( a b c -- result )
    ROT         \ a b c -- b c a
    DUP         \ b c a -- b c a a
    *           \ b c a a -- b c a*a
    +           \ b c a*a -- b c+a*a
    SWAP        \ b c+a*a -- c+a*a b
    /           \ c+a*a b -- (c+a*a)/b
;
```

## Testing

### Run All Tests

```bash
make test
```

### Test Categories

1. **Unit tests**: Individual word behavior (`tests/test_*.f`)
2. **Integration tests**: Word combinations
3. **Regression tests**: Known bug fixes
4. **Compliance tests**: Forth-83 standard conformance

### Writing Tests

```forth
\ tests/test_division.f

\ Test floored division (Forth-83 semantics)
: TEST-DIVISION
    -7 3 /   -3 = ASSERT
    -7 3 MOD  2 = ASSERT
     7 -3 /  -3 = ASSERT
     7 -3 MOD -2 = ASSERT
    ." Division tests passed" CR
;
```

## Documentation

### Code Comments

Every file needs a header:

```nasm
; ============================================================================
; filename.asm - Brief description
; ============================================================================
;
; Longer description of purpose and context.
;
; Author: Your Name
; Date: YYYY-MM-DD
; ============================================================================
```

### Word Documentation

Every Forth word needs:

```forth
\ WORD-NAME  ( stack-effect )
\ Brief description of what it does.
\ 
\ Longer explanation if needed, including:
\ - Edge cases
\ - Errors it can produce
\ - Related words
\ - Example usage
```

## Commit Messages

Format:

```
Short summary (50 chars or less)

Longer description wrapped at 72 characters. Explain:
- What changed
- Why it changed
- Any non-obvious implications

Fixes #123
See also #456
```

Good examples:
- `Fix stack underflow in /MOD when divisor is zero`
- `Add Forth-83 compliant floored division primitives`
- `Document memory map in ARCHITECTURE.md`

Bad examples:
- `Fixed bug`
- `Updates`
- `WIP`

## Communication

### Issues

Use issues for:
- Bug reports (with reproduction steps)
- Feature proposals (with rationale)
- Questions about design decisions

### Discussions

Use GitHub Discussions for:
- General questions
- Ideas that aren't ready for issues
- Community conversation

### Code of Conduct

Be professional. Be respectful. Focus on the work.

We don't have a lengthy code of conduct because we expect contributors to be adults who can work together constructively.

## Recognition

Contributors who make significant contributions will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Considered for "crew" status (ongoing maintainer role)

## Questions?

Open an issue with the "question" label, or start a Discussion.

---

*Thank you for considering contributing to Bare-Metal Forth.*
