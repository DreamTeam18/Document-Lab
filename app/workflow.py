"""Graph assembly; node behavior lives in app.agents."""

from langgraph.graph import END, START, StateGraph

from app.agents import (
    AnsweringAgent,
    AssessmentAgent,
    PlanningAgent,
    RefinementAgent,
    RetrievalAgent,
    SearchService,
    State,
)
from app.agents.budget import BudgetedProvider
from app.agents.contracts import Provider, SearchStorage

# Preserve existing helper imports for callers of app.workflow.
from app.agents.evidence import (
    grounded_citations as grounded_citations,
)
from app.agents.evidence import (
    parse_object as parse_object,
)
from app.agents.evidence import (
    prepare_evidence as prepare_evidence,
)
from app.agents.hyde import HyDEAgent
from app.agents.recovery import ErrorHandlerAgent, GuardedAgent
from app.agents.triage import ConversationalAgent, TriageAgent
from app.agents.web import WebResearchAgent


class Workflow:
    def __init__(
        self,
        providers: Provider,
        storage: SearchStorage,
        stream_answer=False,
        *,
        timeout_seconds: float = 220,
        max_sub_questions: int = 2,
        hyde_enabled: bool = False,
        research_concurrency: int = 2,
        web_client=None,
        research_limiter=None,
        chat_call_limit: int = 6,
        embedding_call_limit: int = 13,
    ):
        self.stream_answer = stream_answer
        self.providers, self.storage = providers, storage
        providers = BudgetedProvider(providers)
        search = SearchService(providers, storage)
        self.triage = TriageAgent(providers)
        self.conversational = ConversationalAgent()
        self.plan = PlanningAgent(providers, max_sub_questions)
        self.hyde = HyDEAgent(providers)
        self.retrieve = RetrievalAgent(search, research_concurrency, research_limiter)
        self.assess = AssessmentAgent(providers, web_fallback=web_client is not None)
        self.refine = RefinementAgent(search)
        self.web = WebResearchAgent(web_client, providers)
        self.answer = AnsweringAgent(providers, stream_answer=stream_answer)
        graph = StateGraph(State)
        names = [
            "web",
            "triage",
            "conversational",
            "plan",
            "retrieve",
            "assess",
            "refine",
            "answer",
        ]
        if hyde_enabled:
            names.append("hyde")
        for name in names:
            graph.add_node(
                name,
                GuardedAgent(
                    name,
                    getattr(self, name),
                    timeout_seconds,
                    chat_call_limit,
                    embedding_call_limit,
                ),
            )
        graph.add_node("error_handler", ErrorHandlerAgent())
        graph.add_edge(START, "triage")
        graph.add_conditional_edges(
            "triage",
            lambda state: (
                "error_handler"
                if state.get("failure")
                else {
                    "greeting": "conversational",
                    "clarify": "conversational",
                    "direct_retrieval": "retrieve",
                    "complex_research": "plan",
                }[state["route"]]
            ),
            {name: name for name in ("error_handler", "conversational", "retrieve", "plan")},
        )
        if hyde_enabled:
            graph.add_conditional_edges(
                "hyde",
                lambda state: "error_handler" if state.get("failure") else "retrieve",
                {"error_handler": "error_handler", "retrieve": "retrieve"},
            )
        for stage, destination in (
            ("plan", "hyde" if hyde_enabled else "retrieve"),
            ("retrieve", "assess"),
            ("refine", "assess"),
            ("web", "answer"),
            ("answer", END),
            ("conversational", END),
        ):
            graph.add_conditional_edges(
                stage,
                lambda state, target=destination: (
                    "error_handler" if state.get("failure") else target
                ),
                {"error_handler": "error_handler", destination: destination},
            )
        graph.add_conditional_edges(
            "assess",
            lambda state: (
                "error_handler"
                if state.get("failure")
                else (
                    "refine"
                    if state["retry"]
                    else "web"
                    if state.get("web_requested")
                    else "answer"
                )
            ),
            {name: name for name in ("error_handler", "refine", "answer", "web")},
        )
        graph.add_conditional_edges(
            "error_handler",
            lambda state: state["recovery_target"],
            {
                "end": END,
                **{name: name for name in ("triage", "plan", "retrieve", "assess", "refine")},
            },
        )
        self.graph = graph.compile()  # PostgreSQL owns conversation persistence.
