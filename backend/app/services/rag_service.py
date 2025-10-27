import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from ..config import settings

# Global variables for RAG components
vectorstore = None
conversation_chain = None
chat_history = {}

# Custom prompt template
CUSTOM_PROMPT = """You are a helpful AI assistant for JD AI Marketing Solutions, a company that helps small businesses implement AI solutions. 

Use the following pieces of context to answer the question at the end. If you don't know the answer or the information is not in the context, politely say that you don't have that specific information and offer to help with something else related to JD AI Marketing Solutions.

Be friendly, professional, and concise. When discussing our services, be enthusiastic but not pushy. Always prioritize providing value to the user.

Context:
{context}

Question: {question}

Helpful Answer:"""

def initialize_rag_system():
    """Initialize the RAG system with document loading and vector store creation."""
    global vectorstore, conversation_chain

    try:
        # Check if OpenAI API key is set
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        # Load documents
        print("Loading documents...")
        loader = DirectoryLoader(
            './documents',
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        documents = loader.load()
        print(f"Loaded {len(documents)} documents")

        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        splits = text_splitter.split_documents(documents)
        print(f"Created {len(splits)} document chunks")

        # Create embeddings and vector store
        print("Creating embeddings and vector store...")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=settings.openai_api_key
        )

        # Check if vector store already exists
        chroma_db_path = "./chroma_db"
        if os.path.exists(chroma_db_path):
            print("Loading existing vector store...")
            vectorstore = Chroma(
                persist_directory=chroma_db_path,
                embedding_function=embeddings
            )
            print("Vector store", vectorstore)
        else:
            print("Creating new vector store...")
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding=embeddings,
                persist_directory=chroma_db_path
            )
        print("Vector store ready")

        # Initialize LLM
        llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=settings.openai_api_key
        )

        # Create custom prompt
        qa_prompt = PromptTemplate.from_template(CUSTOM_PROMPT)

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

        print("RAG system initialized successfully")
        print(f"vectorstore set: {vectorstore is not None}, conversation_chain set: {conversation_chain is not None}")
        return True

    except Exception as e:
        print(f"Error initializing RAG system: {str(e)}")
        return False
