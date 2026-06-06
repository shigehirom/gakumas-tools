import {
  S,
  G,
  ASSIGNMENT_OPERATORS,
  BOOLEAN_OPERATORS,
  ADDITIVE_OPERATORS,
  MULTIPLICATIVE_OPERATORS,
  NUMBER_REGEX,
  FUNCTION_CALL_REGEX,
  STANCES,
  PHASES,
  SOURCE_TYPES,
  RARITIES,
  SKILL_CARD_TYPES,
  SET_OPERATOR,
  GROWABLE_FIELDS,
} from "../constants.js";

export default class Compiler {
  constructor(engine) {
    this.engine = engine;
  }

  compileCondition(tokens) {
    const expr = this.compileExpression(tokens);
    if (!expr) return null;
    try {
      return new Function("state", "resolvers", `return ${expr};`);
    } catch (e) {
      console.warn("Failed to compile condition:", tokens, e);
      return null;
    }
  }

  compileExpression(tokens) {
    if (tokens.length === 1) {
      const token = tokens[0];
      if (token in S) {
        return `state[${S[token]}]`;
      }
      if (NUMBER_REGEX.test(token)) {
        return token;
      }
      if (
        STANCES.includes(token) ||
        PHASES.includes(token) ||
        SOURCE_TYPES.includes(token) ||
        RARITIES.includes(token) ||
        SKILL_CARD_TYPES.includes(token)
      ) {
        return `"${token}"`;
      }
      const match = token.match(FUNCTION_CALL_REGEX);
      if (match && match[1] in this.engine.evaluator.variableResolvers) {
        const name = match[1];
        const args = match[2]
          ? match[2]
              .split(",")
              .map((a) => `"${a.trim()}"`)
              .join(",")
          : "";
        return `resolvers["${name}"](state${args ? "," + args : ""})`;
      }
      if (token in this.engine.evaluator.variableResolvers) {
        return `resolvers["${token}"](state)`;
      }
      return null;
    }

    // Set contains
    if (tokens[1] === SET_OPERATOR) {
      const lhs = this.compileExpression([tokens[0]]);
      if (!lhs) return null;
      return `${lhs}.has("${tokens[2]}")`;
    }

    // Comparators
    const cmpIndex = tokens.findIndex((t) => BOOLEAN_OPERATORS.includes(t));
    if (cmpIndex !== -1) {
      const lhs = this.compileExpression(tokens.slice(0, cmpIndex));
      const rhs = this.compileExpression(tokens.slice(cmpIndex + 1));
      if (!lhs || !rhs) return null;
      let op = tokens[cmpIndex];
      if (op === "==") op = "===";
      if (op === "!=") op = "!==";
      return `(${lhs} ${op} ${rhs})`;
    }

    // Addition, subtraction
    const asIndex = tokens.findIndex((t) => ADDITIVE_OPERATORS.includes(t));
    if (asIndex !== -1) {
      const lhs = this.compileExpression(tokens.slice(0, asIndex));
      const rhs = this.compileExpression(tokens.slice(asIndex + 1));
      if (!lhs || !rhs) return null;
      return `(${lhs} ${tokens[asIndex]} ${rhs})`;
    }

    // Multiplication, division, modulo
    const mdIndex = tokens.findIndex((t) =>
      MULTIPLICATIVE_OPERATORS.includes(t),
    );
    if (mdIndex !== -1) {
      const lhs = this.compileExpression(tokens.slice(0, mdIndex));
      const rhs = this.compileExpression(tokens.slice(mdIndex + 1));
      if (!lhs || !rhs) return null;
      return `(${lhs} ${tokens[mdIndex]} ${rhs})`;
    }

    return null;
  }

  compileAction(tokens) {
    if (tokens.length === 1) {
      const token = tokens[0];
      const match = token.match(FUNCTION_CALL_REGEX);
      if (match) {
        const name = match[1];
        const args = match[2]
          ? match[2]
              .split(",")
              .map((a) => `"${a.trim()}"`)
              .join(",")
          : "";
        if (name in this.engine.executor.specialActions) {
          return new Function(
            "state",
            "card",
            "resolvers",
            "executor",
            `executor.specialActions["${name}"](state${args ? "," + args : ""});`,
          );
        }
      } else if (token in this.engine.executor.specialActions) {
        return new Function(
          "state",
          "card",
          "resolvers",
          "executor",
          `executor.specialActions["${token}"](state);`,
        );
      }
      return null;
    }

    if (ASSIGNMENT_OPERATORS.includes(tokens[1])) {
      const lhs = tokens[0];
      const op = tokens[1];
      const rhsTokens = tokens.slice(2);

      // Handle effectCounter(name) assignments
      const counterMatch = lhs.match(/^effectCounter(?:\((\w+)\))?$/);
      if (counterMatch) {
        // currentInstanceId depends on execution context, hard to bake in.
        return null;
      }

      const rhsExpr = this.compileExpression(rhsTokens);
      if (!rhsExpr) return null;

      const fieldIdx = S[lhs];
      const gFieldIdx = G[`g.${lhs}`];

      // If it's a simple assignment to a state field (no intermediate resolver)
      const intermediateFields = [
        "cost",
        "fixedGenki",
        "fixedStamina",
        "score",
        "goodImpressionTurns",
        "motivation",
        "goodConditionTurns",
        "concentration",
        "genki",
        "stamina",
        "enthusiasm",
        "fullPowerCharge",
      ];

      // Some fields ALWAYS use intermediate resolvers for certain operators
      const usesIntermediate = intermediateFields.includes(lhs);

      if (!usesIntermediate && fieldIdx !== undefined) {
        if (op === "+=") {
          let code = `state[${fieldIdx}] += ${rhsExpr};`;
          if (GROWABLE_FIELDS.includes(fieldIdx)) {
            code = `state[${fieldIdx}] += ${rhsExpr};
                if (card !== null) {
                  const growth = state[${S.cardMap}][card].growth;
                  if (growth && growth[${gFieldIdx}]) state[${fieldIdx}] += growth[${gFieldIdx}];
                }`;
          }
          return new Function("state", "card", "resolvers", "executor", code);
        }
        if (op === "=") {
          return new Function(
            "state",
            "card",
            "resolvers",
            "executor",
            `state[${fieldIdx}] = ${rhsExpr};`,
          );
        }
      }

      // If it uses intermediate resolver, we call it
      if (usesIntermediate) {
        return new Function(
          "state",
          "card",
          "resolvers",
          "executor",
          `const rhs = ${rhsExpr};
           const growth = card !== null ? state[${S.cardMap}][card].growth : {};
           executor.intermediateResolvers["${lhs}"](state, rhs, growth || {}, ${JSON.stringify(rhsTokens)});`,
        );
      }
    }

    return null;
  }

  compileGrowthAction(tokens) {
    if (ASSIGNMENT_OPERATORS.includes(tokens[1])) {
      const lhs = tokens[0];
      const op = tokens[1];
      const rhsTokens = tokens.slice(2);

      if (rhsTokens.length !== 1 || !NUMBER_REGEX.test(rhsTokens[0])) {
        return null;
      }
      const rhs = parseFloat(rhsTokens[0]);
      const gFieldIdx = G[lhs];

      if (gFieldIdx === undefined) return null;

      if (op === "=") {
        return (growth) => {
          growth[gFieldIdx] = rhs;
        };
      } else if (op === "+=") {
        return (growth) => {
          growth[gFieldIdx] = (growth[gFieldIdx] || 0) + rhs;
        };
      } else if (op === "-=") {
        return (growth) => {
          growth[gFieldIdx] = (growth[gFieldIdx] || 0) - rhs;
        };
      }
    }
    return null;
  }
}
