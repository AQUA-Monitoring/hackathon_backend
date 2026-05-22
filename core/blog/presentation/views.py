from rest_framework.generics import ListAPIView, RetrieveAPIView
from core.blog.infra.models import Post 
from .serializer import PostSerializer

class PostListAPIView(ListAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer


class PostDetailAPIView(RetrieveAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    lookup_field = 'id'