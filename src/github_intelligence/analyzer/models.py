"""
Parser-independent models for repository code intelligence.

These immutable models form the contract between the AST parsing layer
and higher-level systems such as the code graph, static analysis,
embeddings, and RAG.

The models intentionally contain no Tree-sitter objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ======================================================================
# Entity Types
# ======================================================================


class CodeEntityType(str, Enum):
    """Supported source-code entity types."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    COMPONENT = "component"
    IMPORT = "import"
    EXPORT = "export"
    VARIABLE = "variable"


# ======================================================================
# Source Location
# ======================================================================


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """
    One-based source-code location.

    Coordinates are one-based so they can be displayed directly
    in editors, reports, and frontend interfaces.
    """

    start_line: int
    start_column: int

    end_line: int
    end_column: int


# ======================================================================
# Code Entity
# ======================================================================


@dataclass(frozen=True, slots=True)
class CodeEntity:
    """
    Normalized representation of a source-code entity.

    Examples:

        function loginUser()
        component OrderPage
        class UserController
        method createOrder()
    """

    entity_type: CodeEntityType

    name: str

    file_path: Path

    location: SourceLocation

    parent: str | None = None

    parameters: tuple[str, ...] = ()

    source: str | None = None

    is_async: bool = False

    @property
    def qualified_name(self) -> str:
        """
        Return a stable name including its parent scope.

        Examples:

            loginUser

            UserController.loginUser

            OrderService.createOrder
        """

        if self.parent:
            return (
                f"{self.parent}."
                f"{self.name}"
            )

        return self.name


# ======================================================================
# Import Reference
# ======================================================================


@dataclass(frozen=True, slots=True)
class ImportReference:
    """
    Represents an ES module import.

    Examples:

        import React from "react";

        import {
            createOrder,
            getCartTotal
        } from "./api.js";

        import {
            createOrder as placeOrder
        } from "./api.js";

        import OrderPage from "./OrderPage.jsx";

        import "./styles.css";
    """

    # Module path.

    source: str

    # File containing the import.

    file_path: Path

    # Location of the import statement.

    location: SourceLocation

    # Names used by the importing file.

    #
    # Example:
    #
    #   import {
    #       createOrder,
    #       getCartTotal
    #   } from "./api.js";
    #
    # becomes:
    #
    #   ("createOrder", "getCartTotal")
    #

    imported_names: tuple[str, ...] = ()

    # Names exported by the imported module that these names
    # correspond to.
    #
    # Usually identical to imported_names.
    #
    # Example:
    #
    #   import {
    #       createOrder as placeOrder
    #   } from "./api.js";
    #
    # imported_names:
    #     ("placeOrder",)
    #
    # imported_symbols:
    #     ("createOrder",)
    #

    imported_symbols: tuple[str, ...] = ()

    # Whether this import represents a default import.
    #
    # Example:
    #
    #   import OrderPage from "./OrderPage.jsx";
    #

    is_default: bool = False

    # Whether this is a namespace import.
    #
    # Example:
    #
    #   import * as api from "./api.js";
    #

    is_namespace: bool = False

    # Optional local aliases.
    #
    # Example:
    #
    #   import {
    #       createOrder as placeOrder
    #   } from "./api.js";
    #
    # becomes:
    #
    #   (("createOrder", "placeOrder"),)
    #

    aliases: tuple[
        tuple[str, str],
        ...,
    ] = ()


# ======================================================================
# Export Reference
# ======================================================================


@dataclass(frozen=True, slots=True)
class ExportReference:
    """
    Represents an ES module export.

    Supported forms include:

        export const createOrder = ...

        export function loginUser() {}

        export default OrderPage

        export default function OrderPage() {}

        export {
            createOrder
        }

        export {
            createOrder as placeOrder
        }

        export {
            createOrder
        } from "./api.js";
    """

    # Normalized exported symbol.

    source: str

    # File containing the export declaration.

    file_path: Path

    # Source location.

    location: SourceLocation

    # Names actually exported by the module.

    #
    # Example:
    #
    #   export {
    #       createOrder,
    #       getCartTotal
    #   };
    #
    # becomes:
    #
    #   ("createOrder", "getCartTotal")
    #

    exported_names: tuple[str, ...] = ()

    # Names of symbols in the source file that are being exported.
    #
    # This differs from exported_names when aliases are used.
    #
    # Example:
    #
    #   export {
    #       createOrder as placeOrder
    #   };
    #
    # exported_names:
    #     ("placeOrder",)
    #
    # exported_symbols:
    #     ("createOrder",)
    #

    exported_symbols: tuple[str, ...] = ()

    # Whether this is a default export.

    is_default: bool = False

    # Optional module source for re-exports.
    #
    # Example:
    #
    #   export {
    #       createOrder
    #   } from "./api.js";
    #
    # reexport_source:
    #
    #   "./api.js"
    #

    reexport_source: str | None = None

    # Alias pairs:
    #
    #   (original_name, exported_name)
    #
    # Example:
    #
    #   export {
    #       createOrder as placeOrder
    #   };
    #
    # becomes:
    #
    #   (("createOrder", "placeOrder"),)
    #

    aliases: tuple[
        tuple[str, str],
        ...,
    ] = ()


# ======================================================================
# Call Reference
# ======================================================================


@dataclass(frozen=True, slots=True)
class CallReference:
    """
    Represents a function or method call.

    Examples:

        createOrder()

        api.createOrder()

        mongoose.connect()

        app.listen()
    """

    # Function/method containing the call.

    caller: str

    # Normalized called symbol.

    callee: str

    # File containing the call.

    file_path: Path

    # Source location of the call.

    location: SourceLocation