# Requirements Document

## Introduction

This document defines the requirements for refactoring PDF-Goon (v1.0.1) into a proper Python library with a CLI entry point. The refactoring follows three guiding principles:

1. **先結構，後代碼** (Structure first, code later) — Architecture and module boundaries must be finalized before implementation begins.
2. **奧卡姆剃刀定理** (Occam's Razor) — Don't add code unless necessary. If a simple function suffices, don't create a class hierarchy.
3. **帕累托法則** (Pareto Principle) — Focus refactoring effort on the core 20% that delivers 80% of value: page analysis, extraction/rendering decisions, and DPI calculation.

The refactoring aims to restructure PDF-Goon as a pip-installable Python library with a clean public API, while preserving all existing functionality and keeping the codebase lean.

## Glossary

- **PDF_Goon**: The Python library and CLI application that processes PDF files to extract or render images
- **Poppler_Tools**: External command-line utilities (pdfimages, pdfinfo, pdftocairo) used for PDF processing
- **Optimizer**: External tools (pingo on Windows, oxipng/jpegoptim on Linux) used for lossless image compression
- **Workspace**: A temporary directory used for intermediate file processing
- **CLI_Layer**: The thin command-line interface module that parses arguments and delegates to the library API
- **Public_API**: The importable Python interface exposed by the pdf_goon package for programmatic use
- **Config**: A dataclass holding validated runtime parameters, constructed from CLI arguments or programmatic input
- **Page_Analyzer**: The function(s) responsible for inspecting PDF page metadata and embedded image information
- **File_Manager**: The function(s) responsible for file operations (move, rename, cleanup, unique path generation)
- **Entry_Point**: The CLI main function that parses arguments, calls the library, and handles top-level errors — containing zero processing logic
- **Guard_Clause**: An early-return conditional check at the start of a function that handles error/edge cases before the main logic
- **Result_Value**: A structured return value (dataclass or tuple) that communicates success or failure information without raising exceptions, used for expected failure modes

## Requirements

### Requirement 1: Library Architecture

**User Story:** As a developer, I want to import pdf_goon as a Python library and use it programmatically, so that I can integrate PDF processing into my own scripts and tools without shelling out to a CLI.

#### Acceptance Criteria

1. THE PDF_Goon SHALL be structured as a Python package with the directory layout: `pdf_goon/__init__.py`, `pdf_goon/core.py`, `pdf_goon/cli.py`, and additional modules as needed
2. THE Public_API SHALL expose a top-level `process` function (or equivalent) that accepts a path and configuration parameters, enabling programmatic use via `import pdf_goon`
3. THE CLI_Layer SHALL be a thin module that parses arguments, constructs a Config, and calls the Public_API without containing any processing logic
4. THE PDF_Goon SHALL be pip-installable via a `pyproject.toml` with a console_scripts entry point for the CLI
5. WHEN the pdf_goon package is imported, THE PDF_Goon SHALL NOT trigger side effects such as argument parsing, tool execution, or output to stdout
6. THE Public_API SHALL return structured results (dataclass or typed dict) rather than printing to stdout, so that callers can inspect processing outcomes programmatically

### Requirement 2: Modular Architecture

**User Story:** As a developer, I want the codebase split into cohesive modules with clear responsibilities, so that I can understand, maintain, and extend each component independently.

#### Acceptance Criteria

1. THE PDF_Goon SHALL organize source code into separate modules for: CLI parsing, tool resolution, PDF analysis, image extraction, page rendering, image optimization, file management, and progress reporting
2. THE PDF_Goon SHALL eliminate global mutable state by passing configuration through function parameters or a Config dataclass
3. WHEN a module is imported independently, THE PDF_Goon SHALL NOT trigger side effects such as argument parsing or tool execution
4. THE PDF_Goon SHALL prefer a flat module structure (single `pdf_goon/` directory) over deep nesting, adding sub-packages only when a module exceeds 300 lines
5. THE PDF_Goon SHALL use simple functions as the default unit of organization, introducing classes only when an object must maintain state across multiple method calls

### Requirement 3: Simplicity and Minimalism

**User Story:** As a developer, I want the refactored codebase to be simpler than the original, so that it is easier to read, debug, and contribute to.

#### Acceptance Criteria

1. THE PDF_Goon SHALL NOT introduce abstract base classes or Protocol definitions unless at least two concrete implementations exist in the codebase
2. THE PDF_Goon SHALL use function parameters for dependency injection (e.g., passing a `run_command` callable) rather than requiring class hierarchies or interface modules
3. THE PDF_Goon SHALL NOT add layers of indirection (wrapper classes, adapter patterns, factory functions) that do not serve a clear, immediate purpose
4. THE PDF_Goon SHALL keep the total module count to the minimum needed for clear separation of concerns — targeting 6-8 modules rather than a proliferation of single-function files
5. WHEN choosing between a simple implementation and a "more extensible" one, THE PDF_Goon SHALL choose the simple implementation unless a concrete, immediate use case justifies the complexity

### Requirement 4: Type Safety and Code Quality

**User Story:** As a developer, I want comprehensive type annotations and consistent code style, so that static analysis tools can catch bugs before runtime.

#### Acceptance Criteria

1. THE PDF_Goon SHALL provide type annotations for all function signatures (parameters and return types)
2. THE PDF_Goon SHALL define dataclasses for structured data (image metadata, page info, processing results)
3. THE PDF_Goon SHALL use an enumeration for processing modes (extract vs render) instead of implicit boolean flags
4. THE PDF_Goon SHALL pass mypy strict type checking without errors

### Requirement 5: Robust Error Handling

**User Story:** As a user, I want clear and actionable error messages when something goes wrong, so that I can diagnose and fix issues without guessing.

#### Acceptance Criteria

1. WHEN a subprocess call fails, THE PDF_Goon SHALL raise a specific exception containing the tool name, exit code, and stderr output
2. THE PDF_Goon SHALL replace all bare except clauses with specific exception types
3. IF a PDF file cannot be processed, THEN THE PDF_Goon SHALL log the error with the file path and reason, and continue processing remaining files
4. IF a required Poppler tool is missing, THEN THE PDF_Goon SHALL exit with a descriptive error message listing the missing tools and installation guidance
5. WHEN an optional optimization tool is unavailable, THE PDF_Goon SHALL log a warning once and disable optimization without repeated warnings

### Requirement 6: Testability

**User Story:** As a developer, I want to write unit tests for PDF processing logic without requiring actual Poppler tools or PDF files, so that tests run fast and reliably in CI.

#### Acceptance Criteria

1. THE PDF_Goon SHALL separate pure logic (DPI calculation, filename generation, image metadata parsing, extraction decision) from side-effectful operations (subprocess calls, file I/O)
2. THE PDF_Goon SHALL accept a `run_command` callable parameter in functions that invoke subprocesses, so that tests can pass a mock implementation
3. THE PDF_Goon SHALL accept a file-operation callable or use pathlib consistently so that file system interactions can be intercepted in tests
4. FOR ALL valid page dimension inputs, parsing pdfinfo output then computing DPI SHALL produce a value within the range [36, 2400]
5. THE PDF_Goon SHALL ensure that each module's tests can run independently using simple function mocks or stubs — without requiring a shared mock framework or interface module

### Requirement 7: Configuration Validation

**User Story:** As a user, I want invalid configuration to be caught early with helpful messages, so that I don't waste time on a run that will fail partway through.

#### Acceptance Criteria

1. WHEN the DPI value is below 36, THE Config SHALL clamp it to 36 and emit a warning
2. WHEN the DPI value is above 2400, THE Config SHALL clamp it to 2400 and emit a warning
3. WHEN the target path does not exist, THE Config SHALL raise a validation error stating the path is invalid
4. WHEN the target path contains no PDF files matching the glob pattern, THE Config SHALL raise a validation error indicating no files were found
5. THE Config SHALL validate all parameters before any PDF processing begins
6. THE Config SHALL be constructable both from CLI arguments and from keyword arguments in Python code, enabling programmatic use

### Requirement 8: Image Optimization

**User Story:** As a user, I want lossless image optimization applied to output files, so that file sizes are reduced without quality loss.

#### Acceptance Criteria

1. WHEN optimization is enabled, THE Optimizer SHALL select the appropriate tool based on the operating system and file format
2. WHEN an optimization subprocess fails, THE Optimizer SHALL log a warning and preserve the unoptimized file rather than failing the entire page
3. THE Optimizer SHALL report bytes saved when verbose mode is enabled
4. THE Optimizer SHALL be implemented as a simple function (e.g., `optimize_image(path, platform)`) rather than requiring a class hierarchy or plugin system

### Requirement 9: Progress Reporting

**User Story:** As a user, I want clear progress feedback during processing, so that I know how far along the batch is.

#### Acceptance Criteria

1. WHILE processing a PDF, THE PDF_Goon SHALL display a progress bar showing current page relative to total pages
2. THE PDF_Goon SHALL display the current file count relative to total files in the batch
3. WHEN verbose mode is enabled, THE PDF_Goon SHALL display per-page details including processing mode (extract/render), DPI used, and output dimensions
4. WHEN used as a library, THE PDF_Goon SHALL accept an optional progress callback function rather than writing directly to stdout

### Requirement 10: Function Decomposition

**User Story:** As a developer, I want each function to have a single clear responsibility and fit within a readable length, so that code reviews and debugging are straightforward.

#### Acceptance Criteria

1. THE PDF_Goon SHALL decompose the monolithic process_single_pdf function into separate functions for: page analysis, extraction decision, image extraction, page rendering, post-processing, and file organization
2. THE PDF_Goon SHALL ensure no function exceeds 50 lines of logic (excluding docstrings and blank lines)
3. THE PDF_Goon SHALL eliminate magic numbers by defining named constants for thresholds (minimum width, DPI bounds, progress bar length)
4. THE PDF_Goon SHALL keep function nesting shallow — no more than one level of helper functions within a module

### Requirement 11: Minimal External Dependencies

**User Story:** As a developer, I want the tool to rely only on the Python standard library (plus required CLI tools), so that installation is simple and there are no fragile third-party package dependencies.

#### Acceptance Criteria

1. THE PDF_Goon SHALL NOT require any third-party Python packages at runtime; all functionality SHALL be implemented using only the Python standard library
2. THE PDF_Goon SHALL replace the optional send2trash dependency with platform-native trash operations using ctypes on Windows (SHFileOperationW) and a freedesktop-compliant trash implementation on Linux, falling back to move-to-delete-folder when neither is available
3. THE PDF_Goon SHALL limit external runtime dependencies to CLI tools only: Poppler utilities (pdfimages, pdfinfo, pdftocairo) and optional optimization tools (pingo on Windows, oxipng/jpegoptim on Linux)
4. FOR development and testing purposes, THE PDF_Goon MAY use third-party packages (pytest, mypy, etc.) but these SHALL NOT be required for normal operation

### Requirement 12: Backward Compatibility

**User Story:** As an existing user, I want the refactored tool to produce identical output for the same inputs, so that my existing workflows are not disrupted.

#### Acceptance Criteria

1. THE PDF_Goon SHALL accept all existing CLI arguments with the same names and default values
2. WHEN given the same PDF input and arguments, THE PDF_Goon SHALL produce output files with the same names and content as v1.0.1
3. THE PDF_Goon SHALL maintain the same exit codes and error output format for existing error conditions
4. THE PDF_Goon SHALL continue to support PyInstaller bundling via sys._MEIPASS detection

### Requirement 13: Temporary File Cleanup

**User Story:** As a user, I want the tool to always clean up temporary files, so that disk space is not wasted by leftover artifacts.

#### Acceptance Criteria

1. WHEN processing completes successfully, THE File_Manager SHALL remove the workspace directory and all its contents
2. IF processing is interrupted by an error, THEN THE File_Manager SHALL still attempt to clean up the workspace directory
3. IF workspace cleanup fails, THEN THE File_Manager SHALL log a warning with the workspace path rather than raising an exception
4. THE File_Manager SHALL use a context manager pattern to guarantee cleanup execution

### Requirement 14: Logging Infrastructure

**User Story:** As a developer, I want structured logging instead of scattered print statements, so that I can control verbosity and direct output to different destinations.

#### Acceptance Criteria

1. THE PDF_Goon SHALL use Python's logging module instead of direct print statements for diagnostic output
2. THE PDF_Goon SHALL support log levels: ERROR for failures, WARNING for degraded operation, INFO for progress, DEBUG for detailed diagnostics
3. WHEN debug mode is enabled, THE PDF_Goon SHALL set the log level to DEBUG and include Poppler stderr output
4. THE PDF_Goon SHALL preserve user-facing progress output (progress bars, summary) on stdout separate from diagnostic logging on stderr

### Requirement 15: Incremental Refactoring Strategy

**User Story:** As a developer, I want to refactor one module at a time without breaking the rest of the system, so that each change is safe, reviewable, and independently verifiable.

#### Acceptance Criteria

1. THE PDF_Goon SHALL structure modules with loose coupling so that each module can be refactored or replaced independently
2. WHEN a module is refactored, THE PDF_Goon SHALL maintain backward-compatible function signatures so that callers continue to function without modification
3. THE PDF_Goon SHALL define inter-module boundaries through function signatures and type annotations rather than requiring shared interface modules
4. THE PDF_Goon SHALL avoid circular dependencies between modules so that each module's dependency graph forms a directed acyclic graph
5. THE PDF_Goon SHALL ensure that the test suite for each module can pass independently of other modules' implementation status (using simple mocks for dependencies)

### Requirement 16: Go-Style Coding Standards

**User Story:** As a developer, I want the codebase to follow a strict, Go-inspired coding style, so that the code is explicit, flat, consistent, and easy to reason about without hidden control flow or implicit behavior.

#### Acceptance Criteria

##### Entry Point Discipline (禁止業務代碼)

1. THE Entry_Point SHALL contain zero processing logic — only argument parsing, a single call to the Public_API, and top-level error handling
2. THE Entry_Point SHALL NOT import or reference any internal module other than the Public_API and the Config dataclass
3. THE Entry_Point SHALL fit within 30 lines of logic (excluding imports and argparse definitions)

##### Explicit Error Handling

4. THE PDF_Goon SHALL handle every error explicitly — no function SHALL silently swallow exceptions or return None to indicate failure without documentation
5. WHEN a function encounters an expected failure mode (file not found, invalid PDF, missing tool), THE PDF_Goon SHALL return a Result_Value rather than raising an exception
6. THE PDF_Goon SHALL reserve exceptions exclusively for unexpected or unrecoverable situations (programming errors, OS-level failures)
7. THE PDF_Goon SHALL NOT use bare `except` clauses or `except Exception` without re-raising or explicit justification in a comment

##### Flat Structure and Early Returns

8. THE PDF_Goon SHALL use Guard_Clauses to check error conditions first and return early, avoiding else-after-return patterns
9. THE PDF_Goon SHALL NOT exceed two levels of indentation nesting within any function body (excluding the function definition itself and a single with-statement or for-loop)
10. WHEN a function exceeds two levels of nesting, THE PDF_Goon SHALL refactor the inner logic into a separate named function

##### Consistency and Single Approach

11. THE PDF_Goon SHALL use dataclasses for all structured data throughout the codebase — not mixing dataclasses with TypedDicts, plain dicts, or named tuples for the same purpose
12. THE PDF_Goon SHALL use a single, consistent error-handling pattern across all modules (Result_Value for expected failures, specific exceptions for unexpected failures)
13. THE PDF_Goon SHALL use consistent function signature patterns: configuration parameters grouped in a Config or dataclass, not passed as loose keyword arguments exceeding three parameters

##### Explicitness Over Magic

14. THE PDF_Goon SHALL NOT use decorators that alter control flow (retry decorators, caching decorators that hide side effects)
15. THE PDF_Goon SHALL NOT use metaclasses, `__getattr__` overrides, or descriptor protocols
16. THE PDF_Goon SHALL NOT use module-level mutable variables — all state SHALL flow through function parameters and return values
17. THE PDF_Goon SHALL NOT use star-imports (`from module import *`) in any module

##### Package-Level Organization

18. THE PDF_Goon SHALL ensure each module has a single, clear purpose identifiable from its filename alone (e.g., `optimize.py` optimizes images, `analyze.py` analyzes PDF pages)
19. THE PDF_Goon SHALL NOT place unrelated functions in a `utils.py` or `helpers.py` catch-all module — each function SHALL belong to the module whose purpose it serves

##### Naming and Documentation

20. THE PDF_Goon SHALL use snake_case for all functions and variables, and PascalCase for all type definitions (dataclasses, enums, type aliases)
21. THE PDF_Goon SHALL use short variable names (1-3 characters) only in scopes of 10 lines or fewer; variables in larger scopes SHALL use descriptive names
22. THE PDF_Goon SHALL provide a one-line docstring for every public function describing what it does (not how)
23. THE PDF_Goon SHALL NOT contain dead code, commented-out code, or TODO comments in the final version

##### Code Cleanliness

24. THE PDF_Goon SHALL ensure all modules pass `ruff check` with no warnings using the default rule set plus the `I` (isort), `UP` (pyupgrade), and `SIM` (simplify) rule categories
25. THE PDF_Goon SHALL ensure consistent import ordering: standard library, then a blank line, then local package imports — no third-party imports at runtime
