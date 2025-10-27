import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from ..config import tenants, TenantConfig

# Global variables for RAG components per tenant
tenant_rag = {}  # tenant_id -> {"vectorstore": ..., "conversation_chain": ..., "chat_history": {}}

# Custom prompt template
CUSTOM_PROMPT = """You are a helpful AI assistant for JD AI Marketing Solutions, a company that helps small businesses implement AI solutions. 

Use the following pieces of context to answer the question at the end. If you don't know the answer or the information is not in the context, politely say that you don't have that specific information and offer to help with something else related to JD AI Marketing Solutions.

Be friendly, professional, and concise. When discussing our services, be enthusiastic but not pushy. Always prioritize providing value to the user.

Context:
{context}

Question: {question}

Helpful Answer:"""

def initialize_rag_system_for_tenant(tenant_id: str, tenant_config: TenantConfig):
    """Initialize the RAG system for a specific tenant."""
    try:
        # Check if OpenAI API key is set
        if not tenant_config.openai_api_key:
            raise ValueError(f"OPENAI_API_KEY not found for tenant {tenant_id}")

        # Load documents
        print(f"Loading documents for tenant {tenant_id}...")
        loader = DirectoryLoader(
            tenant_config.document_path,
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        documents = loader.load()
        print(f"Loaded {len(documents)} documents for tenant {tenant_id}")

        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        splits = text_splitter.split_documents(documents)
        print(f"Created {len(splits)} document chunks for tenant {tenant_id}")

        # Create embeddings and vector store
        print(f"Creating embeddings and vector store for tenant {tenant_id}...")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=tenant_config.openai_api_key
        )

        # Check if vector store already exists
        chroma_db_path = tenant_config.chroma_db_path
        if os.path.exists(chroma_db_path):
            print(f"Loading existing vector store for tenant {tenant_id}...")
            vectorstore = Chroma(
                persist_directory=chroma_db_path,
                embedding_function=embeddings
            )
        else:
            print(f"Creating new vector store for tenant {tenant_id}...")
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding_function=embeddings,
                persist_directory=chroma_db_path
            )
        print(f"Vector store ready for tenant {tenant_id}")

        # Initialize LLM
        llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=tenant_config.openai_api_key
        )

        # Create custom prompt
        qa_prompt = PromptTemplate.from_template(tenant_config.prompt)

        # Create retrieval chain
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        # Configure retriever with better search parameters
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 6}  # Retrieve top 6 most relevant chunks
        )

        conversation_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | qa_prompt
            | llm
            | StrOutputParser()
        )

        tenant_rag[tenant_id] = {
            "vectorstore": vectorstore,
            "conversation_chain": conversation_chain,
            "chat_history": {}
        }

        print(f"RAG system initialized successfully for tenant {tenant_id}")
        return True

    except Exception as e:
        print(f"Error initializing RAG system for tenant {tenant_id}: {str(e)}")
        return False

def get_tenant_rag(tenant_id: str):
    """Get or initialize RAG for a tenant."""
    if tenant_id not in tenant_rag:
        if tenant_id not in tenants:
            raise ValueError(f"Tenant {tenant_id} not configured")
        success = initialize_rag_system_for_tenant(tenant_id, tenants[tenant_id])
        if not success:
            raise RuntimeError(f"Failed to initialize RAG for tenant {tenant_id}")
    return tenant_rag[tenant_id]
