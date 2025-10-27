import os
from pinecone import Pinecone
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from ..config import tenants, TenantConfig, settings

# Initialize Pinecone client
pc = Pinecone(api_key=settings.pinecone_api_key)
index = pc.Index(settings.pinecone_index_name)

# Global variables for RAG components per tenant
tenant_rag = {}  # tenant_id -> {"conversation_chain": ..., "chat_history": {}}

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

        # Create embeddings
        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={'device': 'cpu'}
        )

        # Check if data exists in the namespace
        namespace = tenant_config.pinecone_namespace
        stats = index.describe_index_stats()
        vector_count = stats['namespaces'].get(namespace, {}).get('vector_count', 0)
        if vector_count == 0:
            print(f"No data found for tenant {tenant_id}, upserting documents...")
            # Embed documents
            texts = [doc.page_content for doc in splits]
            vectors = embeddings.embed_documents(texts)
            # Prepare vectors for upsert
            pinecone_vectors = [
                (f"{tenant_id}_{i}", vector, {"text": text}) for i, (vector, text) in enumerate(zip(vectors, texts))
            ]
            index.upsert(vectors=pinecone_vectors, namespace=namespace)
            print(f"Upserted {len(pinecone_vectors)} vectors for tenant {tenant_id}")
        else:
            print(f"Data already exists for tenant {tenant_id} ({vector_count} vectors), skipping upsert")

        print(f"Vector store ready for tenant {tenant_id}")

        # Initialize LLM
        llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=tenant_config.openai_api_key
        )

        # Create custom prompt
        qa_prompt = PromptTemplate.from_template(tenant_config.prompt)

        # Create retrieval function
        def retrieve_docs(query: str, k: int = 6):
            query_vector = embeddings.embed_query(query)
            results = index.query(vector=query_vector, top_k=k, namespace=namespace, include_metadata=True)
            docs = []
            for match in results['matches']:
                text = match['metadata']['text']
                docs.append(Document(page_content=text))
            return docs

        # Create retrieval chain
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        conversation_chain = (
            {"context": lambda x: format_docs(retrieve_docs(x["question"])), "question": RunnablePassthrough()}
            | qa_prompt
            | llm
            | StrOutputParser()
        )

        tenant_rag[tenant_id] = {
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
